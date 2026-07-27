"""The per-authority monitor's activity strip (#121) — the drill-down twin of the
homepage panel, drawn from the same endpoint in single-authority mode.

Per the convention set by test_health_panel, only the server-side wiring is
asserted here; the fetch-and-paint is JS, exercised through the endpoint tests
(the per-day counts the tooltip reads are covered by
test_health_endpoint.test_single_authority_mode_returns_per_day_counts)."""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

import capaggregator
from capaggregator.tests.factories import create_source_authority


class ActivityStripTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def _get(self):
        return self.client.get(reverse("capagg_ingestion_authority_monitor", args=[self.authority.id]))

    def test_the_strip_is_wired_to_the_endpoint_in_single_authority_mode(self):
        response = self._get()

        self.assertContains(response, "activity-strip")
        self.assertContains(response, f"{reverse('capagg_ingestion_health_api')}?authority={self.authority.id}")

    def test_the_strip_ships_the_conformance_marker_and_a_legend(self):
        response = self._get()

        self.assertContains(response, "capagg-cell--defective")
        self.assertContains(response, "Non-conformant CAP")
        self.assertContains(response, "No Signal")

    def test_the_strip_carries_the_labels_its_tooltip_reads(self):
        """The counts are the reason single-authority mode exists — the tooltip
        says "3 stored, 1 withheld" where the dashboard can only say a colour.
        Wording rides on data- attributes so a translation cannot break the JS."""
        response = self._get()

        for label in ["data-label-stored", "data-label-quarantined", "data-label-polls-ok"]:
            self.assertContains(response, label)

    def test_a_failed_fetch_has_a_message_to_show(self):
        """Unlike the dashboard, this page does not re-poll, so a swallowed fetch
        failure would be indistinguishable from an authority with no activity."""
        response = self._get()

        self.assertContains(response, "capagg-strip-error")
        self.assertContains(response, "Could not load activity")


class SharedCellStylingTests(TestCase):
    """One definition of the visual vocabulary, included by both templates —
    otherwise every future change to it gets made in one place and missed in the
    other."""

    TEMPLATE_ROOT = Path(capaggregator.__file__).parent

    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def test_both_pages_ship_the_cell_styling(self):
        for url in [
            reverse("wagtailadmin_home"),
            reverse("capagg_ingestion_authority_monitor", args=[self.authority.id]),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertContains(response, ".capagg-cell--defective::after")

    def test_the_cell_rules_are_defined_in_exactly_one_template(self):
        definitions = [
            path
            for path in self.TEMPLATE_ROOT.rglob("templates/**/*.html")
            if ".capagg-cell--defective::after" in path.read_text()
        ]

        self.assertEqual([path.name for path in definitions], ["_health_cells.html"])
