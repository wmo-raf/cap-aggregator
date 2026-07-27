"""Website links on the Authorities snippet admin: an icon-only column on the
listing and a Website panel on the inspect view. Both read `website_url`, so an
authority with neither a website nor a cap-composer feed shows nothing."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from capaggregator.tests.factories import create_source_authority

WEBSITE = "https://meteo.go.ke"
THIRD_PARTY_FEED = "https://feeds.example.test/ke/cap.atom"


class AuthorityAdminWebsiteLinkTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(user)

    def list_page(self):
        return self.client.get(reverse("wagtailsnippets_capagg_sources_sourceauthority:list"))

    def inspect_page(self, authority):
        return self.client.get(
            reverse("wagtailsnippets_capagg_sources_sourceauthority:inspect", args=[authority.pk])
        )

    def test_listing_renders_the_website_as_an_anchor_not_inert_text(self):
        create_source_authority(name="Kenya Met", website=WEBSITE)

        response = self.list_page()

        self.assertContains(response, "Website")
        self.assertContains(response, f'href="{WEBSITE}"')
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertContains(response, "Kenya Met website (opens in a new tab)")

    def test_listing_cell_is_empty_without_a_website(self):
        create_source_authority(name="Kenya Met", feed_url=THIRD_PARTY_FEED)

        response = self.list_page()

        self.assertContains(response, "Website")  # the column header still renders
        self.assertNotContains(response, "(opens in a new tab)")

    def test_inspect_view_shows_a_website_panel(self):
        authority = create_source_authority(name="Kenya Met", website=WEBSITE)

        response = self.inspect_page(authority)

        self.assertContains(response, f'href="{WEBSITE}"')

    def test_inspect_view_omits_the_panel_without_a_website(self):
        authority = create_source_authority(name="Kenya Met", feed_url=THIRD_PARTY_FEED)

        response = self.inspect_page(authority)

        # The feed URL still renders here, so assert on the panel heading rather
        # than on a URL substring.
        self.assertNotContains(response, '<h2 class="mqtt-actions__header">Website</h2>')
