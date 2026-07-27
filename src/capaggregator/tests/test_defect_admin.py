"""The Alerts menu group: the defect register and the alert inspect view.

Both surfaces are read-only — the defect register is evidence, and an alert is
immutable — so these tests cover what an operator does with them: list, filter
by category and by authority, and follow a defect back to its alert.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from capaggregator.ingestion import categories
from capaggregator.tests.factories import create_alert_defect, create_cap_alert, create_source_authority

DEFECT_LIST = "wagtailsnippets_capagg_alerts_alertdefect:list"
DEFECT_ADD = "wagtailsnippets_capagg_alerts_alertdefect:add"
ALERT_LIST = "wagtailsnippets_capagg_alerts_alert:list"
ALERT_INSPECT = "wagtailsnippets_capagg_alerts_alert:inspect"
ALERT_EDIT = "wagtailsnippets_capagg_alerts_alert:edit"


class AdminSurfaceTestCase(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)


class AlertsMenuGroupTests(AdminSurfaceTestCase):
    def test_both_registers_appear_under_one_alerts_menu_group(self):
        response = self.client.get(reverse("wagtailadmin_home"))

        sidebar = response.content.decode()
        self.assertIn(reverse(DEFECT_LIST), sidebar)
        self.assertIn(reverse(ALERT_LIST), sidebar)


class DefectRegisterTests(AdminSurfaceTestCase):
    def test_the_register_lists_a_defect_with_its_category_and_check(self):
        create_alert_defect(
            authority=self.authority, check_name="polygon-sanity",
            message="polygon ring not closed — will be closed automatically",
        )

        response = self.client.get(reverse(DEFECT_LIST))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "polygon-sanity")
        self.assertContains(response, "Content")

    def test_the_register_filters_by_category(self):
        create_alert_defect(authority=self.authority, check_name="polygon-sanity")
        create_alert_defect(authority=self.authority, check_name="signature")

        response = self.client.get(reverse(DEFECT_LIST), {"category": categories.SIGNATURE})

        self.assertEqual(
            [d.check_name for d in response.context["object_list"]], ["signature"],
        )

    def test_the_register_filters_by_authority(self):
        other = create_source_authority(name="Uganda Met", country="ug",
                                        feed_url="https://ug.test/rss.xml")
        create_alert_defect(authority=self.authority, check_name="polygon-sanity")
        create_alert_defect(authority=other, check_name="expires-required")

        response = self.client.get(reverse(DEFECT_LIST), {"alert__authority": other.id})

        self.assertEqual(
            [d.check_name for d in response.context["object_list"]], ["expires-required"],
        )

    def test_a_defect_links_to_its_alert(self):
        defect = create_alert_defect(authority=self.authority)

        response = self.client.get(reverse(DEFECT_LIST))

        self.assertContains(response, reverse(ALERT_INSPECT, args=[defect.alert_id]))

    def test_the_register_is_read_only(self):
        response = self.client.get(reverse(DEFECT_ADD))

        self.assertNotEqual(response.status_code, 200)

    def test_the_register_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse(DEFECT_LIST))

        self.assertEqual(response.status_code, 302)


class AlertInspectTests(AdminSurfaceTestCase):
    def test_the_alert_list_loads_with_its_defect_count(self):
        create_alert_defect(authority=self.authority)

        response = self.client.get(reverse(ALERT_LIST))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Defects")

    def test_an_alerts_view_lists_its_own_defects(self):
        defect = create_alert_defect(
            authority=self.authority, check_name="expires-required",
            message="info block without <expires> — cannot compute active window",
        )

        response = self.client.get(reverse(ALERT_INSPECT, args=[defect.alert_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "expires-required")
        self.assertContains(response, "cannot compute active window")

    def test_an_alerts_view_shows_its_cap_fields(self):
        alert = create_cap_alert(self.authority, identifier="URN:DISTINCTIVE-ID")

        response = self.client.get(reverse(ALERT_INSPECT, args=[alert.pk]))

        self.assertContains(response, "URN:DISTINCTIVE-ID")

    def test_alerts_are_not_editable(self):
        alert = create_cap_alert(self.authority)

        response = self.client.get(reverse(ALERT_EDIT, args=[alert.pk]))

        self.assertNotEqual(response.status_code, 200)
