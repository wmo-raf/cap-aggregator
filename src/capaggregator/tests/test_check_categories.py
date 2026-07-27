"""The check-name → category mapping, and its coverage invariant.

This is the one seam in the classification work that cannot be reached from
outside: whether every check has a category is a static property of the source,
not something a message can be driven through the pipeline to reveal. The
coverage test scans for check names in the code rather than trusting a
hand-maintained list, so a validator added without a mapping fails the suite.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase

from capaggregator.ingestion import categories, validators


def _reports_a_finding(node: ast.Call) -> bool:
    """True for `<something report-ish>.error(...)` / `.warn(...)` — the two ways
    a check records a finding. Matches a local named `report`/`rpt` and an
    attribute like `self.report`, so renaming the local doesn't silently drop a
    check out of the coverage guarantee below."""
    if not (isinstance(node.func, ast.Attribute) and node.func.attr in ("error", "warn")):
        return False
    target = node.func.value
    if isinstance(target, ast.Name):
        return target.id in ("report", "rpt")
    return isinstance(target, ast.Attribute) and target.attr in ("report", "rpt")


def _check_names_in_source() -> set[str]:
    """Every check name passed as a string literal to a finding call anywhere in
    the ingestion and alerts packages."""
    names = set()
    roots = [Path(validators.__file__).parent, Path(validators.__file__).parent.parent / "alerts"]
    for root in roots:
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if not (isinstance(node, ast.Call) and node.args and _reports_a_finding(node)):
                    continue
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    names.add(first.value)
    return names


class CheckCategoryCoverageTests(SimpleTestCase):
    def test_every_registered_validator_has_a_category(self):
        unmapped = [
            name for name in validators.validator_registry.names()
            if name not in categories.CHECK_CATEGORIES
        ]

        self.assertEqual(unmapped, [], "registered validators without a category mapping")

    def test_every_directly_invoked_check_has_a_category(self):
        found = _check_names_in_source()

        self.assertTrue(found, "the source scan found no check names — the scan itself is broken")
        self.assertEqual(
            sorted(found - set(categories.CHECK_CATEGORIES)), [],
            "checks that report findings without a category mapping",
        )

    def test_every_withholding_check_is_a_real_check(self):
        # A typo in WITHHOLDING_CHECKS would silently publish something we mean
        # to keep back, and nothing else would fail.
        self.assertEqual(
            sorted(categories.WITHHOLDING_CHECKS - set(categories.CHECK_CATEGORIES)), [],
            "withholding checks that no check produces",
        )

    def test_the_mapping_covers_all_seven_categories(self):
        self.assertEqual(
            set(categories.CHECK_CATEGORIES.values()), set(categories.CATEGORY_PRECEDENCE),
        )
        self.assertEqual(len(categories.CATEGORY_PRECEDENCE), 7)

    def test_choices_and_precedence_describe_the_same_vocabulary(self):
        self.assertEqual(
            [value for value, _label in categories.CATEGORY_CHOICES],
            list(categories.CATEGORY_PRECEDENCE),
        )


class PrimaryCategoryTests(SimpleTestCase):
    def test_most_upstream_error_category_wins(self):
        report = {
            "errors": [
                {"check": "polygon-sanity", "message": "..."},
                {"check": "sender", "message": "..."},
                {"check": "references-required", "message": "..."},
            ],
            "warnings": [],
        }

        self.assertEqual(categories.classify_report(report), categories.IDENTITY)

    def test_warnings_are_consulted_only_when_there_are_no_errors(self):
        report = {
            "errors": [{"check": "reissue", "message": "..."}],
            "warnings": [{"check": "signature", "message": "..."}],
        }

        self.assertEqual(categories.classify_report(report), categories.REISSUE)

    def test_a_warning_only_report_still_gets_a_category(self):
        report = {"errors": [], "warnings": [{"check": "expires-required", "message": "..."}]}

        self.assertEqual(categories.classify_report(report), categories.CONTENT)

    def test_a_report_with_no_findings_has_no_category(self):
        self.assertEqual(categories.classify_report({"errors": [], "warnings": []}), "")

    def test_an_unknown_check_is_our_fault_not_the_authoritys(self):
        # The coverage test above stops this happening for real; the fallback
        # exists so a stray name is never reported to an NMHS as their problem.
        self.assertEqual(categories.category_for_check("no-such-check"), categories.INTERNAL)
