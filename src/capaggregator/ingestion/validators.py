"""Layered CAP validation with a pluggable rule registry.

Each validator receives the parsed lxml tree + context and appends findings to
the report. Validation is a conformance record, not a publication gate: a
finding is a defect recorded against the published alert unless it is one of the
few that make publishing impossible or dishonest (`WITHHOLDING_CHECKS` draws
that line; `blocking_findings()` applies it).
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from lxml import etree

from .categories import CHECK_INTERNAL, WITHHOLDING_CHECKS, classify_report

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"
CAP = f"{{{CAP_NS}}}"

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "CAP-v1.2.xsd"
_schema = None  # compiled once per worker


def get_schema() -> etree.XMLSchema:
    global _schema
    if _schema is None:
        _schema = etree.XMLSchema(etree.parse(str(_SCHEMA_PATH)))
    return _schema


def _finding(check: str, message: str, context: dict) -> dict:
    """One finding: prose for a human, plus whatever a renderer can act on.

    Context keys are open-ended and the renderer decides what to do with each —
    `alert` and `chain` become a link to the alert a finding references, `line`
    points the raw-XML view at the offending line. A new check gets that
    treatment by passing the same keys, with no column per check anywhere.
    Omitted entirely when empty, so a report stays readable as JSON.
    """
    finding = {"check": check, "message": message}
    if context:
        finding["context"] = context
    return finding


@dataclass
class ValidationReport:
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)

    def blocking_findings(self) -> list[dict]:
        """The errors that withhold publication.

        Everything else — a fault we can store and serve around — is recorded
        against the alert we publish instead.
        """
        return [e for e in self.errors if e["check"] in WITHHOLDING_CHECKS]

    def blocking_category(self) -> str:
        """The category to file a withheld message under.

        Derived from the blocking findings alone: a defect we would have
        published through must never read as why we refused.
        """
        return classify_report({"errors": self.blocking_findings(), "warnings": []})

    def error(self, check: str, message: str, **context):
        self.errors.append(_finding(check, message, context))

    def warn(self, check: str, message: str, **context):
        self.warnings.append(_finding(check, message, context))

    def blocking_summary(self) -> str:
        """One line naming why the message is unpublished — for the log."""
        return "; ".join(f["message"] for f in self.blocking_findings())

    def as_dict(self) -> dict:
        return {"errors": self.errors, "warnings": self.warnings}


class ValidatorRegistry:
    """Register semantic validators: @validator_registry.register("check-name")"""

    def __init__(self):
        self._validators: dict[str, callable] = {}

    def register(self, name: str):
        def decorator(fn):
            self._validators[name] = fn
            return fn

        return decorator

    def names(self) -> list[str]:
        """Registered check names — every one of them needs a category mapping."""
        return list(self._validators)

    def run_all(self, tree, raw, report: ValidationReport):
        for name, fn in self._validators.items():
            run_check(name, fn, tree, raw, report)


validator_registry = ValidatorRegistry()


def run_check(name: str, fn, tree, raw, report: ValidationReport):
    """Run one check; a crash in it costs the operator that rule, nothing more.

    A crash is recorded against `internal`, not against the rule's own check
    name: our bug filed under (say) polygon-sanity would be reported to an NMHS
    as a defect in their CAP. It is an error rather than a warning — a warning
    would disguise our bug as a minor conformance defect belonging to them —
    but `internal` never withholds, so a broken rule cannot cost an alert its
    publication either.
    """
    try:
        fn(tree, raw, report)
    except Exception as ex:
        report.error(CHECK_INTERNAL, f"validator '{name}' crashed: {ex}")


def run_validators(raw) -> ValidationReport:
    report = ValidationReport()

    # 1. Well-formedness — the one failure that stops the run: with no tree
    #    there is nothing left to check.
    try:
        tree = etree.fromstring(raw.xml.encode())
    except etree.XMLSyntaxError as ex:
        report.error("xml-syntax", str(ex), line=ex.lineno)
        return report

    # 2. XSD. A schema violation no longer ends the run: the message goes
    #    through every remaining check so one ingestion yields the complete
    #    defect list, instead of the operator discovering the next fault only
    #    after fixing this one.
    schema = get_schema()
    if not schema.validate(tree):
        for err in schema.error_log:
            # The line stays in the message as well as in the context: the
            # defect register keeps only the prose, and an operator reading a
            # published alert's defects still needs to know where to look.
            report.error("xsd", f"line {err.line}: {err.message}", line=err.line)

    # 3-5. The directly-invoked checks. They see schema-invalid trees now, so
    #      they carry the same crash guard as the registry: a bug in one must
    #      never cost the operator the rest of the report.
    run_check("sent-parseable", _check_sent, tree, raw, report)
    run_check("signature", _check_signature, tree, raw, report)
    run_check("sender", _check_sender, tree, raw, report)

    # 6. Semantic rules (registry)
    validator_registry.run_all(tree, raw, report)

    return report


def _check_sent(tree, raw, report):
    """<sent> must be readable as a datetime.

    It is a third of the CAP identity triple, so a value we cannot parse leaves
    the alert with no identity to store under, dedup against or supersede — the
    one XSD-adjacent fault that keeps a message unpublished.
    """
    sent = (tree.findtext(f"{CAP}sent") or "").strip()
    try:
        datetime.fromisoformat(sent)
    except ValueError:
        report.error("sent-parseable",
                     f"<sent> value '{sent}' cannot be read as a datetime — the CAP identity "
                     f"triple (sender, identifier, sent) cannot be formed")


def _check_signature(tree, raw, report):
    sig = tree.find("{http://www.w3.org/2000/09/xmldsig#}Signature")
    authority = raw.authority
    policy = authority.signature_policy if authority else "verify_if_present"

    if sig is None:
        if policy == "require":
            report.error("signature", "signature required by policy but not present")
        return

    if policy == "ignore" or not (authority and authority.certificate_pem):
        return

    try:
        from signxml import XMLVerifier

        XMLVerifier().verify(tree, x509_cert=authority.certificate_pem)
    except Exception as ex:
        if policy == "require":
            report.error("signature", f"signature verification failed: {ex}")
        else:
            report.warn("signature", f"signature present but failed verification: {ex}")


def _check_sender(tree, raw, report):
    """Two different questions, so two different checks.

    `attribution` — can we say who sent this at all? An Alert requires a
    non-null authority, so a message no transport could attribute cannot be
    stored, and it stays unpublished.

    `sender` — is the <sender> one this authority told us to expect? Attribution
    already came from the transport (MQTT topic, webhook token, polled feed
    URL), so the allow-list is our configuration rather than a statement about
    the content: a mismatch is a defect on a published alert.
    """
    if not raw.authority:
        report.error("attribution", "message could not be attributed to a registered authority")
        return
    if not raw.authority.sender_values:
        # No allow-list configured — any <sender> is accepted.
        return
    sender = tree.findtext(f"{CAP}sender", default="")
    if sender not in raw.authority.sender_values:
        report.error("sender", f"sender '{sender}' not registered for authority '{raw.authority.slug}'")


# --- Semantic rules -------------------------------------------------------


@validator_registry.register("references-required")
def check_references(tree, raw, report):
    msg_type = tree.findtext(f"{CAP}msgType", default="")
    references = tree.findtext(f"{CAP}references", default="")
    if msg_type in ("Update", "Cancel") and not references.strip():
        report.error("references-required", f"msgType {msg_type} requires <references>")


@validator_registry.register("expires-required")
def check_expires(tree, raw, report):
    # An error, not a warning: the alert publishes either way, but its active
    # window then comes from our default rather than from the author, which is a
    # real defect in the message and worth reporting as one.
    for info in tree.findall(f"{CAP}info"):
        if not (info.findtext(f"{CAP}expires") or "").strip():
            report.error("expires-required", "info block without <expires> — cannot compute active window")


@validator_registry.register("area-for-actual-public")
def check_area(tree, raw, report):
    status = tree.findtext(f"{CAP}status", default="")
    scope = tree.findtext(f"{CAP}scope", default="")
    if status == "Actual" and scope == "Public":
        has_area = any(info.findall(f"{CAP}area") for info in tree.findall(f"{CAP}info"))
        if not has_area:
            report.error("area-for-actual-public", "Actual/Public alert without any <area>")


@validator_registry.register("polygon-sanity")
def check_polygons(tree, raw, report):
    for polygon in tree.iter(f"{CAP}polygon"):
        text = (polygon.text or "").strip()
        if not text:
            continue
        pairs = text.split()
        if len(pairs) < 4:
            report.error("polygon-sanity", "polygon with fewer than 4 coordinate pairs")
            continue
        if pairs[0] != pairs[-1]:
            report.warn("polygon-sanity", "polygon ring not closed — will be closed automatically")
        for pair in pairs:
            try:
                lat, lon = (float(v) for v in pair.split(","))
            except ValueError:
                report.error("polygon-sanity", f"malformed coordinate pair '{pair}'")
                break
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                report.error("polygon-sanity", f"coordinate out of range '{pair}'")
                break


@validator_registry.register("reissue")
def check_reissue(tree, raw, report):
    """Quarantine an alert that repeats content we already hold under a different
    identity triple.

    A publisher that re-serializes an already-disseminated alert with a fresh
    <sent> — and, where <identifier> is derived from <sent>, a fresh identifier —
    looks like a brand-new alert to every layer below us: the byte hash differs,
    the identity triple differs, and with no <references> the lineage resolver has
    nothing to join on. The result is two live ResolvedAlert rows for one hazard.

    Deliberate supersession (<references> present) is exempt — that is what
    msgType Update/Cancel is for, and lineage handles it correctly.
    """
    from datetime import timedelta

    from django.conf import settings

    from capaggregator.alerts.models import Alert
    from capaggregator.alerts.parser import fingerprint_tree

    if raw.authority is None:
        return  # unattributable; the sender check has already errored
    if (tree.findtext(f"{CAP}references") or "").strip():
        return

    fingerprint = fingerprint_tree(tree)
    if not fingerprint:
        return

    sent = (tree.findtext(f"{CAP}sent") or "").strip()
    try:
        sent_dt = datetime.fromisoformat(sent)
    except ValueError:
        return

    window = timedelta(minutes=getattr(settings, "CAP_REISSUE_WINDOW_MINUTES", 60))
    prior = Alert.objects.filter(
        authority=raw.authority,
        content_fingerprint=fingerprint,
        sent__gte=sent_dt - window,
        sent__lte=sent_dt + window,
    ).exclude(sent=sent_dt).order_by("sent").first()

    if prior is not None:
        report.error(
            "reissue",
            f"content identical to alert #{prior.pk} ({prior.identifier}, sent {prior.sent.isoformat()}) "
            f"but re-sent as {(tree.findtext(f'{CAP}identifier') or '').strip()} at {sent} with no "
            f"<references> to it. Either the publisher re-saved an already-disseminated alert "
            f"(upstream bug) or it should have issued msgType=Update.",
            alert=prior.pk,
            chain=prior.chain_id,
        )
