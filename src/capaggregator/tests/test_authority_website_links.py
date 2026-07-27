"""Authority website links on the public, server-rendered surfaces.

All three call sites share `includes/_authority_website_link.html`, whose URL
comes from `SourceAuthority.website_url` — the `website` field, else the origin
of a cap-composer feed. When neither is available the partial must render
nothing at all, never an anchor with an empty href."""

from django.test import TestCase
from django.urls import reverse
from wagtail.models import Page, Site

from capaggregator.home.models import HomePage
from capaggregator.tests.factories import create_event_chain, create_source_authority

WEBSITE = "https://meteo.go.ke"
LINK_ARIA = 'aria-label="Kenya Met website (opens in a new tab)"'
# Feed on a host that is not the authority's own site, so no URL can be derived.
THIRD_PARTY_FEED = "https://feeds.example.test/ke/cap.atom"


class AlertPageWebsiteLinkTests(TestCase):
    def chain_for(self, **authority_kwargs):
        return create_event_chain(create_source_authority(name="Kenya Met", **authority_kwargs))

    def test_detail_page_links_the_issuing_authoritys_website(self):
        chain = self.chain_for(website=WEBSITE)

        response = self.client.get(reverse("alert_detail", args=[chain.pk]))

        self.assertContains(response, f'href="{WEBSITE}"')
        self.assertContains(response, LINK_ARIA)
        self.assertContains(response, 'rel="noopener noreferrer"')

    def test_detail_page_derives_the_link_from_a_composer_feed(self):
        chain = self.chain_for(feed_url="https://meteo.go.ke/api/cap/rss.xml")

        response = self.client.get(reverse("alert_detail", args=[chain.pk]))

        self.assertContains(response, f'href="{WEBSITE}"')

    def test_detail_page_omits_the_link_when_there_is_no_website(self):
        chain = self.chain_for(feed_url=THIRD_PARTY_FEED)

        response = self.client.get(reverse("alert_detail", args=[chain.pk]))

        self.assertNotContains(response, "(opens in a new tab)")
        self.assertNotContains(response, 'href=""')

    def test_version_page_links_the_issuing_authoritys_website(self):
        chain = self.chain_for(website=WEBSITE)

        response = self.client.get(reverse("alert_version", args=[chain.pk, chain.latest_alert.pk]))

        self.assertContains(response, f'href="{WEBSITE}"')
        self.assertContains(response, LINK_ARIA)

    def test_version_page_omits_the_link_when_there_is_no_website(self):
        chain = self.chain_for(feed_url=THIRD_PARTY_FEED)

        response = self.client.get(reverse("alert_version", args=[chain.pk, chain.latest_alert.pk]))

        self.assertNotContains(response, "(opens in a new tab)")


class HomePageWebsiteLinkTests(TestCase):
    def setUp(self):
        root = Page.objects.get(depth=1)
        home = HomePage(title="CAP Aggregator", slug="capagg-home")
        root.add_child(instance=home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = home
        site.save()

    def test_authority_group_header_links_the_website(self):
        create_event_chain(create_source_authority(name="Kenya Met", website=WEBSITE))

        response = self.client.get("/")

        self.assertContains(response, f'href="{WEBSITE}"')
        self.assertContains(response, LINK_ARIA)

    def test_authority_group_header_omits_the_link_when_there_is_no_website(self):
        create_event_chain(create_source_authority(name="Kenya Met", feed_url=THIRD_PARTY_FEED))

        response = self.client.get("/")

        self.assertNotContains(response, "(opens in a new tab)")
