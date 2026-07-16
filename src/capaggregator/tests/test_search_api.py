"""Search API contract pieces the frontend depends on."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from capaggregator.tests.factories import create_event_chain, create_source_authority


class SearchApiTests(TestCase):
    def test_results_carry_the_chain_id_for_detail_links(self):
        chain = create_event_chain(create_source_authority())

        response = self.client.get(reverse("alert_search"))

        self.assertEqual(response.status_code, 200)
        feature = response.json()["results"]["features"][0]
        self.assertEqual(feature["properties"]["chain"], chain.pk)


class AuthorityPropertiesTests(TestCase):
    """The Country > Authority table grouping needs the issuing authority's
    display name and primary country on each feature — no client-side join."""

    def test_results_carry_the_issuing_authority_name_and_country(self):
        authority = create_source_authority(name="Kenya Met Department", country="ke")
        create_event_chain(authority)

        response = self.client.get(reverse("alert_search"))

        self.assertEqual(response.status_code, 200)
        properties = response.json()["results"]["features"][0]["properties"]
        self.assertEqual(properties["authority_name"], "Kenya Met Department")
        self.assertEqual(properties["authority_country"], "KE")
        self.assertEqual(properties["authority_country_name"], "Kenya")


class EffectiveRangeTests(TestCase):
    """The Table view browses alert history by effective-date *range* —
    deliberately different semantics from the map's point-in-time `t`."""

    def setUp(self):
        self.authority = create_source_authority()
        base = timezone.now()

        def chain_on(days_ago, headline):
            eff = base - timedelta(days=days_ago)
            return create_event_chain(
                self.authority,
                sent=eff,
                infos=[{"effective": eff, "expires": eff + timedelta(hours=6), "headline": headline}],
            )

        self.old = chain_on(20, "Twenty days ago")
        self.mid = chain_on(10, "Ten days ago")
        self.recent = chain_on(2, "Two days ago")
        self.base = base

    def search(self, **params):
        response = self.client.get(reverse("alert_search"), params)
        self.assertEqual(response.status_code, 200)
        return [f["properties"]["headline"] for f in response.json()["results"]["features"]]

    def iso_days_ago(self, days):
        return (self.base - timedelta(days=days)).isoformat()

    def test_range_returns_only_alerts_effective_within_it(self):
        headlines = self.search(
            effective_from=self.iso_days_ago(12), effective_to=self.iso_days_ago(5)
        )

        self.assertEqual(headlines, ["Ten days ago"])

    def test_range_mode_includes_expired_alerts(self):
        """Archive semantics: a range query must not apply the active-now default."""
        headlines = self.search(effective_from=self.iso_days_ago(30))

        self.assertEqual(len(headlines), 3)

    def test_date_only_bounds_are_inclusive_of_the_end_day(self):
        target_day = (self.base - timedelta(days=2)).date().isoformat()

        headlines = self.search(effective_from=target_day, effective_to=target_day)

        self.assertEqual(headlines, ["Two days ago"])

    def test_range_composes_with_facet_filters(self):
        headlines = self.search(effective_from=self.iso_days_ago(30), severity="Minor")

        self.assertEqual(headlines, [])  # all factory chains are Severe

    def test_range_params_are_documented_in_the_schema(self):
        response = self.client.get(reverse("api_schema"))

        content = response.content.decode()
        self.assertIn("effective_from", content)
        self.assertIn("effective_to", content)


class SeverityOrderingTests(TestCase):
    """order=severity ranks worst-first (Extreme→...→Unknown) so severity-grouped
    lists stay contiguous across pagination; -effective breaks ties."""

    def setUp(self):
        self.authority = create_source_authority()
        base = timezone.now() - timedelta(hours=1)

        def chain(severity, hours_ago, headline):
            eff = base - timedelta(hours=hours_ago)
            return create_event_chain(
                self.authority,
                sent=eff,
                infos=[{
                    "severity": severity, "headline": headline,
                    "effective": eff, "expires": eff + timedelta(days=2),
                }],
            )

        chain("Minor", 0, "Minor newest")
        chain("Extreme", 5, "Extreme old")
        chain("Severe", 3, "Severe newer")
        chain("Severe", 4, "Severe older")

    def headlines(self, **params):
        response = self.client.get(reverse("alert_search"), params)
        self.assertEqual(response.status_code, 200)
        return [f["properties"]["headline"] for f in response.json()["results"]["features"]]

    def test_order_severity_ranks_worst_first_then_newest(self):
        self.assertEqual(
            self.headlines(order="severity"),
            ["Extreme old", "Severe newer", "Severe older", "Minor newest"],
        )

    def test_default_ordering_stays_newest_first(self):
        self.assertEqual(
            self.headlines(),
            ["Minor newest", "Severe newer", "Severe older", "Extreme old"],
        )


class CountryOrderingTests(TestCase):
    """order=country sorts by the issuing authority's country, then authority
    name, then newest-first — so Country > Authority grouped, paginated lists
    stay globally contiguous."""

    def setUp(self):
        base = timezone.now() - timedelta(hours=1)

        def chain(authority, hours_ago, headline):
            eff = base - timedelta(hours=hours_ago)
            return create_event_chain(
                authority,
                sent=eff,
                infos=[{"headline": headline, "effective": eff, "expires": eff + timedelta(days=2)}],
            )

        za_provincial = create_source_authority(name="ZA Provincial Service", country="za")
        za_national = create_source_authority(name="SA Weather Service", country="za")
        kenya = create_source_authority(name="Kenya Met Department", country="ke")

        chain(za_provincial, 0, "ZA provincial newest")
        chain(za_national, 2, "SAWS older")
        chain(za_national, 1, "SAWS newer")
        chain(kenya, 3, "Kenya oldest")

    def headlines(self, **params):
        response = self.client.get(reverse("alert_search"), params)
        self.assertEqual(response.status_code, 200)
        return [f["properties"]["headline"] for f in response.json()["results"]["features"]]

    def test_order_country_groups_by_country_then_authority_then_newest(self):
        self.assertEqual(
            self.headlines(order="country"),
            ["Kenya oldest", "SAWS newer", "SAWS older", "ZA provincial newest"],
        )
