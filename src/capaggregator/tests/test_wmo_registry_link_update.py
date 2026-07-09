"""WMO Registry picker (issue #30): applying a selection links a manually-added
authority to its registry entry, and updates an already-linked authority whose
official feed URL has changed."""

from django.test import TestCase

from capaggregator.sources.models import SourceAuthority
from capaggregator.sources.wmo_registry import (
    STATUS_UP_TO_DATE,
    apply_registry_selection,
    derive_registry_view,
)

from .factories import create_source_authority
from .test_wmo_registry_apply import entry


class ApplyLinkTests(TestCase):
    def test_linking_stamps_the_registry_guid_and_feed_onto_the_existing_authority(self):
        existing = create_source_authority(
            name="Hand Added Met", feed_url="https://ha.example/cap.xml", sender_values=["pinned@ha.example"]
        )
        e = entry(guid="urn:oid:link", name="Registry Name", feed_url="https://ha.example/cap.xml")

        summary = apply_registry_selection([e], {e.guid})

        existing.refresh_from_db()
        self.assertEqual(summary.linked, 1)
        self.assertEqual(summary.created, 0)
        self.assertEqual(existing.wmo_guid, "urn:oid:link")
        self.assertEqual(existing.wmo_feed_url, "https://ha.example/cap.xml")
        # Nothing else is touched — not even the name (registry name is ignored on link).
        self.assertEqual(existing.name, "Hand Added Met")
        self.assertEqual(existing.sender_values, ["pinned@ha.example"])
        self.assertEqual(SourceAuthority.objects.count(), 1)

    def test_a_linked_entry_reads_up_to_date(self):
        create_source_authority(name="Hand Added Met", feed_url="https://ha.example/cap.xml")
        e = entry(guid="urn:oid:link", feed_url="https://ha.example/cap.xml")

        apply_registry_selection([e], {e.guid})

        [row] = derive_registry_view([e])
        self.assertEqual(row.status, STATUS_UP_TO_DATE)

    def test_a_trailing_slash_feed_variant_links_instead_of_duplicating(self):
        create_source_authority(name="Hand Added Met", feed_url="https://ha.example/cap.xml")
        # Registry lists the same feed with a trailing slash — must still match.
        e = entry(guid="urn:oid:link", feed_url="https://ha.example/cap.xml/")

        summary = apply_registry_selection([e], {e.guid})

        self.assertEqual(summary.linked, 1)
        self.assertEqual(summary.created, 0)
        self.assertEqual(SourceAuthority.objects.count(), 1)


class ApplyUpdateTests(TestCase):
    def _linked_authority(self, **kwargs):
        return create_source_authority(
            name="Linked Met",
            feed_url="https://old.example/cap.xml",
            wmo_guid="urn:oid:upd",
            wmo_feed_url="https://old.example/cap.xml",
            feed_etag='"abc"',
            feed_last_modified="Mon, 01 Jan 2026 00:00:00 GMT",
            **kwargs,
        )

    def test_update_moves_the_authority_to_the_new_feed_and_clears_conditional_get(self):
        authority = self._linked_authority()
        e = entry(guid="urn:oid:upd", feed_url="https://new.example/cap.xml")

        summary = apply_registry_selection([e], {e.guid})

        authority.refresh_from_db()
        self.assertEqual(summary.updated, 1)
        self.assertEqual(authority.feed_url, "https://new.example/cap.xml")
        self.assertEqual(authority.wmo_feed_url, "https://new.example/cap.xml")
        self.assertEqual(authority.feed_etag, "")
        self.assertEqual(authority.feed_last_modified, "")

    def test_update_preserves_admin_owned_fields(self):
        authority = self._linked_authority(
            sender_values=["pinned@x"], feed_poll_interval_minutes=7, active=False
        )
        e = entry(guid="urn:oid:upd", name="Ignored New Name", feed_url="https://new.example/cap.xml")

        apply_registry_selection([e], {e.guid})

        authority.refresh_from_db()
        self.assertEqual(authority.sender_values, ["pinned@x"])
        self.assertEqual(authority.name, "Linked Met")
        self.assertEqual(authority.feed_poll_interval_minutes, 7)
        self.assertFalse(authority.active)
