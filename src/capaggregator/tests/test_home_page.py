"""Wagtail HomePage: hero + CTA, cached stats strip, latest alerts (issue #48)."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from wagtail.models import Page, Site

from capaggregator.home.models import HomePage
from capaggregator.tests.factories import create_event_chain, create_source_authority


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
        # default hero look when no image is uploaded
        self.assertContains(response, "capagg-hero--default")

    def test_stats_strip_matches_seeded_data(self):
        create_event_chain(self.authority)
        create_event_chain(self.authority, is_cancelled=True)  # not active
        create_source_authority(name="Uganda Met", country="ug", sender_values=["u@x"])
        create_source_authority(name="Retired", country="tz", sender_values=["r@x"], active=False)

        response = self.client.get("/")

        stats = response.context["stats"]
        self.assertEqual(stats["active_alerts"], 1)
        self.assertEqual(stats["authorities"], 2)  # active only
        self.assertEqual(stats["countries"], 2)  # ke + ug

    def test_latest_alerts_are_listed_with_detail_links(self):
        older = create_event_chain(
            self.authority,
            sent=timezone.now() - timedelta(hours=2),
            infos=[{"headline": "Older flood warning"}],
        )
        newest = create_event_chain(self.authority, infos=[{"headline": "Newest cyclone warning"}])

        response = self.client.get("/")

        content = response.content.decode()
        self.assertIn("Newest cyclone warning", content)
        self.assertIn(reverse("alert_detail", args=[newest.pk]), content)
        self.assertLess(content.index("Newest cyclone warning"), content.index("Older flood warning"))
        self.assertIn(reverse("alert_detail", args=[older.pk]), content)

    def test_stats_are_cached_briefly(self):
        create_event_chain(self.authority)
        first = self.client.get("/").context["stats"]

        create_event_chain(self.authority, infos=[{"headline": "Another"}])
        second = self.client.get("/").context["stats"]

        self.assertEqual(first, second)  # served from cache within the TTL

    def test_hero_copy_is_editor_controlled(self):
        self.home.hero_heading = "Every warning, one map"
        self.home.save_revision().publish()

        response = self.client.get("/")

        self.assertContains(response, "Every warning, one map")
