"""Health dashboard 4/5: the homepage activity panel. Per AC, only the server-side
wiring is asserted (the panel renders on the admin home, wired to the endpoint);
the fetch-and-paint behaviour is JS, exercised via the endpoint tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class HealthPanelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def test_panel_renders_on_the_admin_homepage_wired_to_the_endpoint(self):
        response = self.client.get(reverse("wagtailadmin_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "capagg-health-panel")
        self.assertContains(response, reverse("capagg_ingestion_health_api"))
