"""WMO Registry picker (issue #29): applying a selection bulk-creates NEW
authorities from parsed registry entries."""

from django.test import TestCase

from capaggregator.sources.models import SourceAuthority
from capaggregator.sources.wmo_registry import RegistryEntry, apply_registry_selection

from .factories import create_source_authority


def entry(guid="urn:oid:1", name="National Met Service", country="KE",
          feed_url="https://nms.example/cap/en.xml", contact_email="ops@nms.example", abbrev="nms",
          country_name="Kenya"):
    return RegistryEntry(guid=guid, name=name, country=country, feed_url=feed_url,
                         contact_email=contact_email, abbrev=abbrev, country_name=country_name)


class ApplyCreatesAuthorityTests(TestCase):
    def test_selected_new_entry_creates_an_authority_with_mapped_fields(self):
        e = entry()

        apply_registry_selection([e], {e.guid})

        authority = SourceAuthority.objects.get(wmo_guid=e.guid)
        self.assertEqual(authority.name, "National Met Service")
        self.assertEqual(authority.country, "KE")
        self.assertEqual(authority.feed_url, "https://nms.example/cap/en.xml")
        self.assertEqual(authority.contact_email, "ops@nms.example")
        self.assertEqual(authority.wmo_feed_url, "https://nms.example/cap/en.xml")

    def test_created_authority_is_active_with_an_empty_sender_allowlist(self):
        e = entry()

        apply_registry_selection([e], {e.guid})

        authority = SourceAuthority.objects.get(wmo_guid=e.guid)
        self.assertTrue(authority.active)
        self.assertEqual(authority.sender_values, [])

    def test_only_selected_entries_are_created(self):
        chosen = entry(guid="urn:oid:chosen", name="Chosen Met", feed_url="https://a.example/cap.xml")
        ignored = entry(guid="urn:oid:ignored", name="Ignored Met", feed_url="https://b.example/cap.xml")

        summary = apply_registry_selection([chosen, ignored], {chosen.guid})

        self.assertEqual(summary.created, 1)
        self.assertTrue(SourceAuthority.objects.filter(wmo_guid="urn:oid:chosen").exists())
        self.assertFalse(SourceAuthority.objects.filter(wmo_guid="urn:oid:ignored").exists())

    def test_entries_that_slugify_alike_get_distinct_slugs(self):
        a = entry(guid="urn:oid:a", name="Meteo Service", feed_url="https://a.example/cap.xml")
        b = entry(guid="urn:oid:b", name="Meteo Service", feed_url="https://b.example/cap.xml")

        summary = apply_registry_selection([a, b], {a.guid, b.guid})

        self.assertEqual(summary.created, 2)
        slugs = set(SourceAuthority.objects.values_list("slug", flat=True))
        self.assertEqual(len(slugs), 2)

    def test_selected_entry_matching_an_existing_authority_is_not_duplicated(self):
        create_source_authority(name="Existing", feed_url="https://dup.example/cap.xml")
        e = entry(guid="urn:oid:dup", name="Same Feed Body", feed_url="https://dup.example/cap.xml")

        summary = apply_registry_selection([e], {e.guid})

        self.assertEqual(summary.created, 0)
        self.assertEqual(SourceAuthority.objects.filter(feed_url="https://dup.example/cap.xml").count(), 1)

    def test_a_created_entry_no_longer_reads_as_new(self):
        from capaggregator.sources.wmo_registry import STATUS_NEW, derive_registry_view

        e = entry()
        apply_registry_selection([e], {e.guid})

        [row] = derive_registry_view([e])
        self.assertNotEqual(row.status, STATUS_NEW)
