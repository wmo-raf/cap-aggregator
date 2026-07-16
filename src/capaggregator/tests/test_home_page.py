"""Wagtail HomePage: hero + CTA, current-situation stat cards, and all active
alerts grouped per authority (issues #48 + homepage improvements round)."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from wagtail.models import Page, Site

from capaggregator.home.models import HomePage
from capaggregator.tests.factories import (
    create_event_chain,
    create_source_authority,
    create_source_event,
)


def install_home_page(**kwargs):
    root = Page.objects.get(depth=1)
    home = HomePage(title="CAP Aggregator", slug="capagg-home", **kwargs)
    root.add_child(instance=home)
    site = Site.objects.get(is_default_site=True)
    site.root_page = home
    site.save()
    return home


class FreshSetupTests(TestCase):
    """A brand-new database must serve the landing page at / out of the box —
    the 0002_create_homepage data migration replaces Wagtail's placeholder."""

    def test_root_serves_the_homepage_without_manual_setup(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "capagg-hero")
        self.assertNotContains(response, "Welcome to your new Wagtail site!")


class HomePageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.home = install_home_page()
        self.authority = create_source_authority(name="Kenya Met")

    def test_serves_at_site_root_with_hero_and_map_cta(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "capagg-hero")
        self.assertContains(response, 'href="/explorer/"')
        self.assertContains(response, "capagg-hero--default")

    def test_hero_copy_is_editor_controlled(self):
        self.home.hero_heading = "Every warning, one map"
        self.home.save_revision().publish()

        response = self.client.get("/")

        self.assertContains(response, "Every warning, one map")


class StatCardsTests(TestCase):
    def setUp(self):
        cache.clear()
        install_home_page()
        self.kenya = create_source_authority(name="Kenya Met")

    def stats(self):
        return self.client.get("/").context["stats"]

    def test_active_alerts_with_severity_breakdown(self):
        create_event_chain(self.kenya, infos=[{"severity": "Severe"}])
        create_event_chain(self.kenya, infos=[{"severity": "Severe", "headline": "Second"}])
        create_event_chain(self.kenya, infos=[{"severity": "Minor", "headline": "Third"}])
        create_event_chain(self.kenya, is_cancelled=True)  # not counted

        stats = self.stats()

        self.assertEqual(stats["active_alerts"], 3)
        by_severity = {i["severity"]: i["count"] for i in stats["alert_severity_counts"]}
        self.assertEqual(by_severity, {"Extreme": 0, "Severe": 2, "Moderate": 0, "Minor": 1})

    def test_countries_with_alerts_classified_by_worst_severity(self):
        # Kenya: Severe + Moderate → one country, classified Severe
        create_event_chain(self.kenya, infos=[{"severity": "Severe"}])
        create_event_chain(self.kenya, infos=[{"severity": "Moderate", "headline": "Lesser"}])
        # Uganda: covered but quiet
        create_source_authority(name="Uganda Met", country="ug", sender_values=["u@x"])

        stats = self.stats()

        self.assertEqual(stats["countries_with_alerts"], 1)
        self.assertEqual(stats["countries_covered"], 2)
        by_severity = {i["severity"]: i["count"] for i in stats["country_severity_counts"]}
        self.assertEqual(by_severity["Severe"], 1)
        self.assertEqual(by_severity["Moderate"], 0)  # worst wins — Kenya counted once
        # the card shows current-vs-covered
        self.assertContains(self.client.get("/"), "of 2 covered")

    def test_system_status_operational_within_window(self):
        create_source_event(authority=self.kenya, ok=True)

        stats = self.stats()

        self.assertEqual(stats["status"], "operational")
        self.assertIsNotNone(stats["last_check"])

    def test_system_status_degraded_when_contact_is_stale(self):
        create_source_event(
            authority=self.kenya, ok=True, occurred_at=timezone.now() - timedelta(hours=2)
        )

        self.assertEqual(self.stats()["status"], "degraded")

    def test_system_status_unknown_without_any_successful_contact(self):
        create_source_event(authority=self.kenya, ok=False)

        self.assertEqual(self.stats()["status"], "unknown")

    def test_stats_are_cached_briefly(self):
        create_event_chain(self.kenya)
        first = self.stats()

        create_event_chain(self.kenya, infos=[{"headline": "Another"}])
        second = self.stats()

        self.assertEqual(first, second)  # served from cache within the TTL


class AlertGroupTests(TestCase):
    def setUp(self):
        cache.clear()
        install_home_page()
        self.kenya = create_source_authority(name="Kenya Met")
        self.uganda = create_source_authority(name="Uganda Met", country="ug", sender_values=["u@x"])

    def test_groups_order_worst_severity_first(self):
        create_event_chain(self.kenya, infos=[{"severity": "Severe", "headline": "Kenya severe"}])
        create_event_chain(self.uganda, infos=[{"severity": "Extreme", "headline": "Uganda extreme"}])

        groups = self.client.get("/").context["alert_groups"]

        self.assertEqual([g["authority"].name for g in groups], ["Uganda Met", "Kenya Met"])
        self.assertEqual(groups[0]["country_name"], "Uganda")
        self.assertEqual(groups[0]["flag"], "🇺🇬")

    def test_all_alerts_rendered_first_two_visible_rest_expandable(self):
        base = timezone.now()
        for i in range(4):
            create_event_chain(
                self.kenya,
                sent=base - timedelta(hours=i),
                infos=[{"headline": f"Kenya alert {i}"}],
            )

        response = self.client.get("/")
        content = response.content.decode()

        # every alert is in the HTML (server-rendered)
        for i in range(4):
            self.assertIn(f"Kenya alert {i}", content)
        # the two beyond the visible limit are collapsed
        self.assertEqual(content.count("data-extra"), 2)
        self.assertContains(response, "View 2 more")
        # newest first: alert 0 is visible, alert 3 is collapsed
        visible_region, collapsed_region = content.split("data-extra", 1)
        self.assertIn("Kenya alert 0", visible_region)
        self.assertIn("Kenya alert 3", collapsed_region)

    def test_each_alert_links_to_its_detail_page(self):
        chain = create_event_chain(self.kenya)

        self.assertContains(self.client.get("/"), reverse("alert_detail", args=[chain.pk]))

    def test_severity_filter_panel_and_filterable_markup(self):
        create_event_chain(self.kenya, infos=[{"severity": "Severe"}])

        response = self.client.get("/")
        content = response.content.decode()

        self.assertEqual(content.count("data-severity-filter"), 4)  # one checkbox per level
        self.assertIn('data-severity="severe"', content)  # items are filterable client-side
        self.assertIn("data-group-count", content)

    def test_stats_legend_explains_the_severity_colors(self):
        response = self.client.get("/")

        self.assertContains(response, "Severity color legend")
        for level in ("Extreme", "Severe", "Moderate", "Minor"):
            self.assertContains(response, f"severity-dot--{level.lower()}")


class HomeMapSectionTests(TestCase):
    """Map + list split: the list is the server-rendered union of active and
    upcoming alerts; client JS derives the time buttons from each item's
    data-effective/data-expires and toggles visibility for the selected t."""

    def setUp(self):
        cache.clear()
        install_home_page()
        self.kenya = create_source_authority(name="Kenya Met")

    def upcoming_chain(self, hours_ahead, headline="Upcoming storm"):
        effective = timezone.now() + timedelta(hours=hours_ahead)
        return create_event_chain(
            self.kenya,
            infos=[{"effective": effective, "expires": effective + timedelta(hours=6), "headline": headline}],
        )

    def test_map_shell_time_control_and_tiles_config_are_rendered(self):
        create_event_chain(self.kenya)

        content = self.client.get("/").content.decode()

        self.assertIn('id="capagg-home-map"', content)
        self.assertIn("data-time-control", content)
        self.assertIn('id="capagg-config"', content)  # json_script the map JS boots from

    def test_upcoming_alerts_are_rendered_hidden_with_time_attributes(self):
        create_event_chain(self.kenya, infos=[{"headline": "Active now"}])
        self.upcoming_chain(30)

        content = self.client.get("/").content.decode()

        self.assertIn("Upcoming storm", content)  # in the HTML for client-side time travel
        self.assertIn("data-upcoming", content)  # ...but hidden at t=now without JS
        self.assertIn("data-effective=", content)
        self.assertIn("data-expires=", content)

    def test_upcoming_alerts_do_not_change_stats_or_expand_counts(self):
        create_event_chain(self.kenya, infos=[{"headline": "Active now"}])
        for hours in (10, 20, 30):
            self.upcoming_chain(hours, headline=f"Upcoming {hours}")

        response = self.client.get("/")

        self.assertEqual(response.context["stats"]["active_alerts"], 1)  # stats stay active-only
        group = response.context["alert_groups"][0]
        self.assertEqual(group["active_count"], 1)
        self.assertEqual(group["extra_count"], 0)  # "View N more" counts active alerts only
        self.assertNotIn("data-extra", response.content.decode())