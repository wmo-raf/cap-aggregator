"""WMO Registry picker (continent grouping): group_registry_rows turns the flat
rows into display sections — a flat 'Added' section first, then Region ▸ Sub-region
for the not-added rows, then a flat 'Unavailable' section last."""

from django.test import SimpleTestCase

from capaggregator.sources.registry import (
    STATUS_ALREADY_EXISTS,
    STATUS_INVALID_COUNTRY,
    STATUS_NEW,
    STATUS_NO_FEED,
    RegistryRow,
    group_registry_rows,
)

from .test_wmo_registry_apply import entry


def row(status, country, country_name, name, authority_id=None):
    return RegistryRow(
        entry=entry(guid=f"g:{name}", name=name, country=country, country_name=country_name),
        status=status,
        selectable=status in {STATUS_NEW, STATUS_ALREADY_EXISTS},
        authority_id=authority_id,
    )


class GroupRegistryRowsTests(SimpleTestCase):
    def test_in_system_rows_form_a_flat_added_group_first(self):
        added = row(STATUS_ALREADY_EXISTS, "KE", "Kenya", "KMD", authority_id=1)
        new = row(STATUS_NEW, "SA", "Saudi Arabia", "NCM")

        groups = group_registry_rows([new, added])

        self.assertEqual(groups[0].kind, "added")
        self.assertEqual(groups[0].label, "Added")
        self.assertEqual(groups[0].subgroups[0].label, None)
        self.assertEqual(groups[0].subgroups[0].rows, [added])

    def test_added_group_is_sorted_by_country_then_name(self):
        a = row(STATUS_ALREADY_EXISTS, "MZ", "Mozambique", "INAM", authority_id=1)
        b = row(STATUS_ALREADY_EXISTS, "KE", "Kenya", "KMD", authority_id=2)

        groups = group_registry_rows([a, b])

        self.assertEqual(groups[0].subgroups[0].rows, [b, a])  # Kenya before Mozambique

    def test_new_rows_are_grouped_by_region_then_subregion(self):
        ke = row(STATUS_NEW, "KE", "Kenya", "KMD")  # Africa / Sub-Saharan Africa
        sa = row(STATUS_NEW, "SA", "Saudi Arabia", "NCM")  # Asia / Western Asia

        groups = group_registry_rows([sa, ke])
        regions = [(g.label, [s.label for s in g.subgroups]) for g in groups if g.kind == "region"]

        self.assertEqual(regions, [("Africa", ["Sub-Saharan Africa"]), ("Asia", ["Western Asia"])])

    def test_overall_order_is_added_then_regions_alpha_then_unavailable(self):
        added = row(STATUS_ALREADY_EXISTS, "KE", "Kenya", "KMD", authority_id=1)
        europe = row(STATUS_NEW, "NL", "Netherlands", "KNMI")
        africa = row(STATUS_NEW, "NG", "Nigeria", "NiMet")
        dead = row(STATUS_NO_FEED, "SY", "Syria", "SyMet")

        kinds = [(g.kind, g.label) for g in group_registry_rows([dead, europe, added, africa])]

        self.assertEqual(kinds, [("added", "Added"), ("region", "Africa"), ("region", "Europe"), ("unavailable", "Unavailable")])

    def test_non_addable_rows_form_the_unavailable_group(self):
        no_feed = row(STATUS_NO_FEED, "SY", "Syria", "SyMet")
        invalid = row(STATUS_INVALID_COUNTRY, None, "Netherlands Antilles", "AntMet")

        groups = group_registry_rows([no_feed, invalid])

        self.assertEqual(groups[-1].kind, "unavailable")
        self.assertEqual(len(groups[-1].subgroups[0].rows), 2)

    def test_a_country_with_no_region_falls_into_other_after_named_regions(self):
        antarctica = row(STATUS_NEW, "AQ", "Antarctica", "AntSurvey")  # empty region in the dataset
        africa = row(STATUS_NEW, "KE", "Kenya", "KMD")

        region_labels = [g.label for g in group_registry_rows([antarctica, africa]) if g.kind == "region"]

        self.assertEqual(region_labels, ["Africa", "Other"])
