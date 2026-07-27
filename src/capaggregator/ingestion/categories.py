"""Category vocabulary for validation findings.

Every finding carries the name of the check that produced it. This module is the
single place that maps a check name to one of seven categories, so an operator
can tell what *kind* of problem a message has from a list column without opening
it.

There is deliberately no `uncategorised` value: `test_check_categories` asserts
that every registered semantic validator and every directly-invoked check has an
entry here, so an unmapped check is a build failure rather than a silent data
state.
"""

from django.utils.translation import gettext_lazy as _

SCHEMA = "schema"
IDENTITY = "identity"
SIGNATURE = "signature"
REISSUE = "reissue"
LINEAGE = "lineage"
CONTENT = "content"
INTERNAL = "internal"

# Ordered by how upstream the failure is. Nothing downstream is trustworthy when
# something upstream failed, so when a message has findings in several
# categories the earliest entry here is the one worth showing.
CATEGORY_PRECEDENCE = (SCHEMA, IDENTITY, SIGNATURE, REISSUE, LINEAGE, CONTENT, INTERNAL)

CATEGORY_CHOICES = (
    (SCHEMA, _("Schema")),
    (IDENTITY, _("Identity")),
    (SIGNATURE, _("Signature")),
    (REISSUE, _("Re-issue")),
    (LINEAGE, _("Lineage")),
    (CONTENT, _("Content")),
    (INTERNAL, _("Internal")),
)

# Check name for our own faults — a validator that crashes today, an unexpected
# storage failure later. Findings filed under it are never reported to an
# authority: our bug must not reach an NMHS as a defect in their CAP.
CHECK_INTERNAL = "internal"

CHECK_CATEGORIES = {
    "xml-syntax": SCHEMA,
    "xsd": SCHEMA,
    "sent-parseable": SCHEMA,
    "datetime-format": CONTENT,
    "field-length": CONTENT,
    "attribution": IDENTITY,
    "sender": IDENTITY,
    "signature": SIGNATURE,
    "reissue": REISSUE,
    "references-required": LINEAGE,
    "expires-required": CONTENT,
    "area-for-actual-public": CONTENT,
    "polygon-sanity": CONTENT,
    CHECK_INTERNAL: INTERNAL,
}


# The only checks whose errors keep a message unpublished. Every other finding
# is recorded as a defect against the alert we publish: the authority already
# published it on their own site and feed, so withholding it over a fault we can
# store and serve around makes us the only place the warning is missing.
#
# Each entry earns its place by making publication impossible or dishonest:
#   xml-syntax     — no tree, so no Alert can exist
#   attribution    — an Alert requires a non-null authority
#   sent-parseable — the CAP identity triple cannot be formed without <sent>
#   signature      — errors here come only from a `require` policy, where we
#                    cannot show the message came from the authority at all
#   reissue        — the content is already live under another identity;
#                    publishing would fork one hazard into two resolved alerts
#
# Adding a check therefore defaults to *publishing* it, which is the intended
# bias. `CHECK_CATEGORIES` above is the list every check must appear in, and the
# coverage test forces an author of a new check through this module.
WITHHOLDING_CHECKS = frozenset({"xml-syntax", "attribution", "sent-parseable", "signature", "reissue"})


def category_for_check(check: str) -> str:
    """Category of the check that produced a finding.

    An unmapped name falls back to `internal` rather than to a category we would
    report to an authority — a check we forgot to map is our fault, not theirs.
    The coverage test exists so this fallback is never reached in practice.
    """
    return CHECK_CATEGORIES.get(check, INTERNAL)


def classify_report(report: dict) -> str:
    """The one category to show for a whole validation report.

    Errors decide it — they are why a message is withheld — and warnings are
    consulted only when there are no errors. Within either set the most upstream
    category wins, per `CATEGORY_PRECEDENCE`. Returns "" for a report with no
    findings at all.
    """
    for severity in ("errors", "warnings"):
        found = {category_for_check(f.get("check", "")) for f in (report.get(severity) or [])}
        for category in CATEGORY_PRECEDENCE:
            if category in found:
                return category
    return ""
