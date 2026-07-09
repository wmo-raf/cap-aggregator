"""Status derivation matches parsed registry entries against existing
SourceAuthority rows — by wmo_guid first, then by feed_url — to decide what the
picker shows and whether a row is selectable."""

from django.test import TestCase

from capaggregator.sources.registry import RegistryEntry, derive_registry_view

from .factories import create_source_authority


def _entry(**kwargs):
    defaults = {
        "guid": "urn:oid:1",
        "name": "Test Authority",
        "country": "KE",
        "feed_url": "https://example.test/rss.xml",
        "contact_email": "ops@example.test",
        "abbrev": "ta",
    }
    defaults.update(kwargs)
    return RegistryEntry(**defaults)


class StatusLabelTests(TestCase):
    def test_new_reads_not_added_and_already_exists_reads_added(self):
        new_row = derive_registry_view([_entry()])[0]
        create_source_authority(name="Existing", feed_url="https://dup.test/rss.xml")
        existing_row = derive_registry_view([_entry(guid="urn:oid:dup", feed_url="https://dup.test/rss.xml")])[0]

        self.assertEqual(new_row.status_label, "Not Added")
        self.assertEqual(existing_row.status_label, "Added")


class DeriveRegistryViewTests(TestCase):
    def test_unmatched_entry_is_new(self):
        rows = derive_registry_view([_entry()])

        self.assertEqual(rows[0].status, "NEW")
        self.assertTrue(rows[0].selectable)

    def test_matching_by_feed_url_without_a_wmo_guid_is_already_exists(self):
        authority = create_source_authority(feed_url="https://example.test/rss.xml", wmo_guid="")

        rows = derive_registry_view([_entry(guid="urn:oid:unlinked")])

        self.assertEqual(rows[0].status, "ALREADY_EXISTS")
        self.assertTrue(rows[0].selectable)
        self.assertEqual(rows[0].authority_id, authority.id)

    def test_matching_by_guid_with_the_same_live_feed_is_up_to_date(self):
        create_source_authority(
            feed_url="https://example.test/rss.xml",
            wmo_guid="urn:oid:1",
            wmo_feed_url="https://example.test/rss.xml",
        )

        rows = derive_registry_view([_entry(guid="urn:oid:1", feed_url="https://example.test/rss.xml")])

        self.assertEqual(rows[0].status, "UP_TO_DATE")
        self.assertFalse(rows[0].selectable)

    def test_matching_by_guid_with_a_changed_live_feed_needs_update(self):
        create_source_authority(
            feed_url="https://example.test/old.xml",
            wmo_guid="urn:oid:1",
            wmo_feed_url="https://example.test/old.xml",
        )

        rows = derive_registry_view([_entry(guid="urn:oid:1", feed_url="https://example.test/new.xml")])

        self.assertEqual(rows[0].status, "NEEDS_UPDATE")
        self.assertTrue(rows[0].selectable)

    def test_entry_with_no_feed_url_is_non_selectable(self):
        rows = derive_registry_view([_entry(feed_url=None)])

        self.assertEqual(rows[0].status, "NO_FEED")
        self.assertFalse(rows[0].selectable)

    def test_entry_with_no_country_is_non_selectable(self):
        rows = derive_registry_view([_entry(country=None)])

        self.assertEqual(rows[0].status, "INVALID_COUNTRY")
        self.assertFalse(rows[0].selectable)

    def test_guid_match_takes_precedence_over_feed_url_match(self):
        # Guid-linked authority on a different feed, plus an unrelated authority
        # that happens to share the live feed URL: the guid match wins.
        create_source_authority(
            name="Linked",
            feed_url="https://example.test/linked.xml",
            wmo_guid="urn:oid:1",
            wmo_feed_url="https://example.test/linked.xml",
        )
        create_source_authority(name="Coincidental", feed_url="https://example.test/rss.xml", wmo_guid="")

        rows = derive_registry_view([_entry(guid="urn:oid:1", feed_url="https://example.test/rss.xml")])

        self.assertEqual(rows[0].status, "NEEDS_UPDATE")
