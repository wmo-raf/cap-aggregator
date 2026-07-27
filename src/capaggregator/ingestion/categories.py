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
    "sender": IDENTITY,
    "signature": SIGNATURE,
    "reissue": REISSUE,
    "references-required": LINEAGE,
    "expires-required": CONTENT,
    "area-for-actual-public": CONTENT,
    "polygon-sanity": CONTENT,
    CHECK_INTERNAL: INTERNAL,
}


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
