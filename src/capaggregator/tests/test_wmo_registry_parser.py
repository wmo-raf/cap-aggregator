"""Pure parser for the WMO Register of Alerting Authorities feed. Uses lxml
directly (not feedparser) because the feed's namespaced elements — repeated
raa:capAlertFeed with xml:lang, raa:authorityAbbrev, iso:countrycode — are not
reliably exposed by feedparser. No network, no DB."""

from django.test import TestCase

from capaggregator.sources.wmo_registry import parse_wmo_registry

from .cap_samples import WMO_REGISTRY_SAMPLE_XML


class ParseWmoRegistryTests(TestCase):
    def setUp(self):
        self.entries = parse_wmo_registry(WMO_REGISTRY_SAMPLE_XML)

    def test_prefers_the_english_capalertfeed_when_multiple_languages_are_listed(self):
        entry = next(e for e in self.entries if e.guid == "urn:oid:2.49.0.0.682.0")

        self.assertEqual(entry.feed_url, "https://ncm.gov.sa/en/cap-alerts")

    def test_falls_back_to_the_only_listed_feed_when_it_is_not_english(self):
        entry = next(e for e in self.entries if e.guid == "urn:oid:2.49.0.0.508.0")

        self.assertEqual(entry.feed_url, "https://cap-sources.s3.amazonaws.com/mz-inam-pt/rss.xml")

    def test_feed_url_is_none_when_no_capalertfeed_is_present(self):
        entry = next(e for e in self.entries if e.guid == "urn:oid:2.49.0.0.760.0")

        self.assertIsNone(entry.feed_url)

    def test_strips_the_leading_country_prefix_from_the_title(self):
        entry = next(e for e in self.entries if e.guid == "urn:oid:2.49.0.0.682.0")

        self.assertEqual(entry.name, "National Center for Meteorology")

    def test_keeps_the_whole_title_when_there_is_no_country_prefix(self):
        entry = next(e for e in self.entries if e.guid == "urn:oid:2.49.0.0.555.0")

        self.assertEqual(entry.name, "Testland Meteorological Service")

    def test_captures_the_country_name_prefix_from_the_title(self):
        entry = next(e for e in self.entries if e.guid == "urn:oid:2.49.0.0.508.0")

        self.assertEqual(entry.country_name, "Mozambique")

    def test_country_name_falls_back_to_the_code_when_the_title_has_no_prefix(self):
        entry = next(e for e in self.entries if e.guid == "urn:oid:2.49.0.0.555.0")

        self.assertEqual(entry.country_name, "KE")

    def test_maps_the_iso_alpha3_countrycode_to_alpha2(self):
        entry = next(e for e in self.entries if e.guid == "urn:oid:2.49.0.0.682.0")

        self.assertEqual(entry.country, "SA")

    def test_country_is_none_when_the_alpha3_code_is_unmappable(self):
        entry = next(e for e in self.entries if e.guid == "urn:oid:2.49.0.0.999.0")

        self.assertIsNone(entry.country)

    def test_contact_email_and_abbrev_come_from_author_and_authorityabbrev(self):
        entry = next(e for e in self.entries if e.guid == "urn:oid:2.49.0.0.682.0")

        self.assertEqual(entry.contact_email, "n.al-orfi@ncm.gov.sa")
        self.assertEqual(entry.abbrev, "ncm")

    def test_parses_every_item_in_the_feed(self):
        self.assertEqual(len(self.entries), 5)
