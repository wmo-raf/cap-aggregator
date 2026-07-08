"""The Authorities snippet index gets a secondary "Add from WMO Registry"
header button beside the default Add button (issue #28)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class WmoRegistryHeaderButtonTests(TestCase):
    def _index_url(self):
        return reverse("wagtailsnippets_capagg_sources_sourceauthority:list")

    def test_superuser_sees_the_add_from_wmo_registry_button(self):
        user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(user)

        response = self.client.get(self._index_url())

        self.assertContains(response, "Add from WMO Registry")
        self.assertContains(response, reverse("capagg_sources_wmo_registry"))
