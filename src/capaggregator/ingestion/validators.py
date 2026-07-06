"""Layered CAP validation with a pluggable rule registry.

Each validator receives the parsed lxml tree + context and appends findings to
the report. Errors → quarantine; warnings → stored with the alert and counted
against the source's quality score.
"""

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"
CAP = f"{{{CAP_NS}}}"

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "CAP-v1.2.xsd"
_schema = None  # compiled once per worker


def get_schema() -> etree.XMLSchema:
    global _schema
    if _schema is None:
        _schema = etree.XMLSchema(etree.parse(str(_SCHEMA_PATH)))
    return _schema


@dataclass
class ValidationReport:
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def error(self, check: str, message: str):
        self.errors.append({"check": check, "message": message})

    def warn(self, check: str, message: str):
        self.warnings.append({"check": check, "message": message})

    def error_summary(self) -> str:
        return "; ".join(e["message"] for e in self.errors)

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

    def run_all(self, tree, raw, report: ValidationReport):
        for name, fn in self._validators.items():
            try:
                fn(tree, raw, report)
            except Exception as ex:  # a broken rule must not kill the pipeline
                report.warn(name, f"validator crashed: {ex}")


validator_registry = ValidatorRegistry()


def run_validators(raw) -> ValidationReport:
    report = ValidationReport()

    # 1. Well-formedness + XSD
    try:
        tree = etree.fromstring(raw.xml.encode())
    except etree.XMLSyntaxError as ex:
        report.error("xml-syntax", str(ex))
        return report

    schema = get_schema()
    if not schema.validate(tree):
        for err in schema.error_log:
            report.error("xsd", f"line {err.line}: {err.message}")
        return report

    # 2. Signature (policy per authority)
    _check_signature(tree, raw, report)

    # 3. Identity: sender must match the authority bound to the topic/token
    _check_sender(tree, raw, report)

    # 4. Semantic rules (registry)
    validator_registry.run_all(tree, raw, report)

    return report


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
    if not raw.authority:
        report.error("sender", "message could not be attributed to a registered authority")
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
    for info in tree.findall(f"{CAP}info"):
        if not (info.findtext(f"{CAP}expires") or "").strip():
            report.warn("expires-required", "info block without <expires> — cannot compute active window")


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
