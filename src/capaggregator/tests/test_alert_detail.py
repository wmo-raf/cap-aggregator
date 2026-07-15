"""Public alert detail page: chain-canonical URL serving the resolved state of
one event chain, server-rendered (indexable, complete without JavaScript)."""

from django.test import TestCase
from django.urls import reverse

from capaggregator.tests.factories import create_event_chain, create_source_authority


class AlertDetailTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    def detail(self, chain):
        return self.client.get(reverse("alert_detail", args=[chain.pk]))

    def test_detail_page_shows_the_resolved_alert(self):
        chain = create_event_chain(self.authority)

        response = self.detail(chain)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flooding expected along the coast")
        self.assertContains(response, "Flood Warning")
        self.assertContains(response, "Severe")
        self.assertContains(response, "Kenya Met")
        self.assertContains(response, "Move to higher ground.")

    def test_unknown_chain_returns_404(self):
        response = self.client.get(reverse("alert_detail", args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_multi_language_alert_renders_every_info_block_with_its_language(self):
        chain = create_event_chain(
            self.authority,
            infos=[
                {"language": "en", "headline": "Flooding expected along the coast"},
                {"language": "fr", "event": "Alerte inondation", "headline": "Inondations attendues sur la côte",
                 "description": "De fortes pluies sont attendues.", "instruction": "Rejoignez les hauteurs."},
            ],
        )

        response = self.detail(chain)

        self.assertContains(response, "Flooding expected along the coast")
        self.assertContains(response, "Inondations attendues sur la côte")
        self.assertContains(response, "Rejoignez les hauteurs.")
        # each block is labelled with its language so readers can find theirs
        self.assertContains(response, 'lang="en"')
        self.assertContains(response, 'lang="fr"')

    def test_cancelled_chain_shows_an_unmistakable_banner(self):
        chain = create_event_chain(self.authority, is_cancelled=True)

        response = self.detail(chain)

        self.assertContains(response, "cancelled")
        self.assertContains(response, "alert-status-banner")

    def test_expired_alert_shows_an_expired_banner(self):
        from datetime import timedelta

        from django.utils import timezone

        past = timezone.now() - timedelta(days=2)
        chain = create_event_chain(
            self.authority,
            sent=past,
            infos=[{"effective": past, "expires": past + timedelta(hours=6)}],
        )

        response = self.detail(chain)

        self.assertContains(response, "expired")
        self.assertContains(response, "alert-status-banner")

    def test_live_alert_shows_no_status_banner(self):
        chain = create_event_chain(self.authority)

        response = self.detail(chain)

        self.assertNotContains(response, "alert-status-banner")

    def test_detail_links_to_the_raw_cap_xml_of_the_latest_message(self):
        chain = create_event_chain(self.authority)
        xml_url = reverse("alert_xml", args=[chain.pk])

        response = self.detail(chain)

        self.assertContains(response, xml_url)

    def test_xml_endpoint_serves_the_original_signed_cap_document(self):
        chain = create_event_chain(self.authority, xml='<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>abc</identifier></alert>')

        response = self.client.get(reverse("alert_xml", args=[chain.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/xml")
        self.assertIn("urn:oasis:names:tc:emergency:cap:1.2", response.content.decode())

    def test_xml_endpoint_404s_for_unknown_chain(self):
        response = self.client.get(reverse("alert_xml", args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_detail_uses_the_public_base_template_with_header_and_footer(self):
        chain = create_event_chain(self.authority)

        response = self.detail(chain)

        self.assertContains(response, "<header")
        self.assertContains(response, "<footer")
        # logo links home; header navigates to the explorer
        self.assertContains(response, 'alt="CAP Aggregator"')
        self.assertContains(response, "/explorer/")

    def test_detail_embeds_area_geometry_for_the_progressive_map(self):
        from django.contrib.gis.geos import MultiPolygon, Polygon

        geom = MultiPolygon(Polygon(((30, -5), (30, 5), (40, 5), (40, -5), (30, -5))))
        chain = create_event_chain(self.authority, resolved_kwargs={"geom": geom})

        response = self.detail(chain)

        self.assertContains(response, 'id="capagg-area-geojson"')
        self.assertContains(response, "MultiPolygon")

    def test_detail_omits_the_map_when_there_is_no_geometry(self):
        chain = create_event_chain(self.authority)

        response = self.detail(chain)

        self.assertNotContains(response, 'id="capagg-area-geojson"')

    def test_chain_url_is_stable_across_supersession(self):
        """The same URL keeps serving the chain after an Update replaces the
        original message — exactly when shared links must not break."""
        from capaggregator.tests.factories import create_cap_alert

        chain = create_event_chain(self.authority)
        url = reverse("alert_detail", args=[chain.pk])

        update = create_cap_alert(
            self.authority, chain=chain, msg_type="Update",
            infos=[{"headline": "Flooding now subsiding", "severity": "Moderate"}],
        )
        chain.latest_alert = update
        chain.save(update_fields=["latest_alert"])
        resolved = chain.resolved
        resolved.latest_alert = update
        resolved.headline = "Flooding now subsiding"
        resolved.severity = "Moderate"
        resolved.save()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flooding now subsiding")
        self.assertNotContains(response, "Flooding expected along the coast")
