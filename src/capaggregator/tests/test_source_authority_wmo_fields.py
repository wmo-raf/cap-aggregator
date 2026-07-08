"""SourceAuthority gains wmo_guid/wmo_feed_url (issue #28) so the WMO Registry
picker can stamp registry linkage and detect feed drift. wmo_guid is unique only
among non-empty values — many authorities are added without going through the
picker and all share the blank default."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from .factories import create_source_authority


class SourceAuthorityWmoFieldsTests(TestCase):
    def test_multiple_authorities_may_have_a_blank_wmo_guid(self):
        create_source_authority(name="A", feed_url="https://a.example.test/rss.xml", wmo_guid="")
        create_source_authority(name="B", feed_url="https://b.example.test/rss.xml", wmo_guid="")

    def test_wmo_guid_is_unique_among_non_empty_values(self):
        create_source_authority(name="A", feed_url="https://a.example.test/rss.xml", wmo_guid="urn:oid:1")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_source_authority(name="B", feed_url="https://b.example.test/rss.xml", wmo_guid="urn:oid:1")
