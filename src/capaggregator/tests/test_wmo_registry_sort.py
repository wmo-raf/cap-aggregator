"""WMO Registry picker (enhancements): presentation-order sort — in-system rows
first, then NEW, then non-addable; each group by country name then authority name."""

from django.test import SimpleTestCase

from capaggregator.sources.registry import (
    STATUS_ALREADY_EXISTS,
    STATUS_INVALID_COUNTRY,
    STATUS_NEEDS_UPDATE,
    STATUS_NEW,
    STATUS_NO_FEED,
    STATUS_UP_TO_DATE,
    RegistryRow,
    sort_registry_rows,
)

from .test_wmo_registry_apply import entry


def row(status, country_name, name, authority_id=None):
    return RegistryRow(
        entry=entry(guid=f"g:{country_name}:{name}", name=name, country="KE", country_name=country_name),
        status=status,
        selectable=status in {STATUS_NEW, STATUS_ALREADY_EXISTS, STATUS_NEEDS_UPDATE},
        authority_id=authority_id,
    )


class SortRegistryRowsTests(SimpleTestCase):
    def test_in_system_rows_come_first_then_new_then_non_addable(self):
        new_z = row(STATUS_NEW, "Zambia", "Z Met")
        up_to_date = row(STATUS_UP_TO_DATE, "Kenya", "K Met", authority_id=1)
        no_feed = row(STATUS_NO_FEED, "Angola", "Ang Met")
        new_a = row(STATUS_NEW, "Angola", "A Met")
        already = row(STATUS_ALREADY_EXISTS, "Uganda", "U Met", authority_id=2)

        ordered = sort_registry_rows([new_z, up_to_date, no_feed, new_a, already])

        self.assertEqual(ordered, [up_to_date, already, new_a, new_z, no_feed])

    def test_needs_update_is_grouped_with_the_in_system_rows(self):
        needs_update = row(STATUS_NEEDS_UPDATE, "Fiji", "F Met", authority_id=3)
        new_row = row(STATUS_NEW, "Chad", "C Met")

        ordered = sort_registry_rows([new_row, needs_update])

        self.assertEqual(ordered, [needs_update, new_row])

    def test_invalid_country_sorts_to_the_bottom_group(self):
        invalid = row(STATUS_INVALID_COUNTRY, "Someplace", "S Met")
        new_row = row(STATUS_NEW, "Zimbabwe", "Z Met")

        ordered = sort_registry_rows([invalid, new_row])

        self.assertEqual(ordered, [new_row, invalid])
