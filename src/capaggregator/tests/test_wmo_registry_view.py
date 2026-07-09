"""Thin integration test for the WMO Registry picker admin view: registry fetch
is mocked (no network), the view wires fetch -> parse -> derive_registry_view
and renders rows/badges."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .cap_samples import WMO_REGISTRY_SAMPLE_XML


class WmoRegistryPickerViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def _url(self):
        return reverse("capagg_sources_wmo_registry")

    @patch("capaggregator.sources.admin_views.fetch_wmo_registry")
    def test_renders_a_row_per_registry_entry_with_its_status_badge(self, fetch):
        fetch.return_value = (WMO_REGISTRY_SAMPLE_XML, None)

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "National Center for Meteorology")
        self.assertContains(response, "NEW")

    @patch("capaggregator.sources.admin_views.fetch_wmo_registry")
    def test_a_non_selectable_row_has_no_checkbox(self, fetch):
        fetch.return_value = (WMO_REGISTRY_SAMPLE_XML, None)

        response = self.client.get(self._url())

        # The Syrian entry has no capAlertFeed, so it must not be selectable.
        self.assertContains(response, "NO FEED")
        self.assertNotContains(response, 'value="urn:oid:2.49.0.0.760.0"')

    @patch("capaggregator.sources.admin_views.fetch_wmo_registry")
    def test_renders_a_submit_form_for_the_selection(self, fetch):
        fetch.return_value = (WMO_REGISTRY_SAMPLE_XML, None)

        response = self.client.get(self._url())

        self.assertContains(response, 'method="post"')
        self.assertContains(response, "Add selected")

    @patch("capaggregator.sources.admin_views.fetch_wmo_registry")
    def test_renders_an_error_state_when_the_registry_is_unreachable(self, fetch):
        fetch.return_value = (None, "Could not reach the WMO Register of Alerting Authorities. Try again later.")

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Could not reach the WMO Register of Alerting Authorities")

    @patch("capaggregator.sources.admin_views.fetch_wmo_registry")
    def test_the_refresh_button_requests_a_forced_refetch(self, fetch):
        fetch.return_value = (WMO_REGISTRY_SAMPLE_XML, None)

        self.client.get(self._url(), {"refresh": "1"})

        fetch.assert_called_once_with(refresh=True)

    def test_requires_login(self):
        self.client.logout()

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 302)

    @patch("capaggregator.sources.admin_views.fetch_wmo_registry")
    def test_posting_a_selection_creates_authorities_and_redirects_to_the_list(self, fetch):
        from capaggregator.sources.models import SourceAuthority

        fetch.return_value = (WMO_REGISTRY_SAMPLE_XML, None)

        response = self.client.post(self._url(), {"guid": ["urn:oid:2.49.0.0.682.0"]})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, reverse("wagtailsnippets_capagg_sources_sourceauthority:list")
        )
        self.assertTrue(SourceAuthority.objects.filter(wmo_guid="urn:oid:2.49.0.0.682.0").exists())
