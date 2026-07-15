"""Alert detail extras: lineage timeline, rendered version pages, OpenGraph
cards and related alerts (issue #45)."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from capaggregator.tests.factories import create_cap_alert, create_event_chain, create_source_authority


def add_update(chain, msg_type="Update", headline="Updated flood warning", severity="Moderate", offset_hours=1):
    """Append a message to the chain and roll the denormalized state forward,
    mirroring what the lineage resolver does."""
    update = create_cap_alert(
        chain.authority,
        chain=chain,
        msg_type=msg_type,
        sent=chain.latest_alert.sent + timedelta(hours=offset_hours),
        infos=[{"headline": headline, "severity": severity}],
    )
    chain.latest_alert = update
    chain.is_cancelled = chain.is_cancelled or msg_type == "Cancel"
    chain.save()
    resolved = chain.resolved
    resolved.latest_alert = update
    resolved.headline = headline
    resolved.severity = severity
    resolved.msg_type = msg_type
    resolved.is_cancelled = chain.is_cancelled
    resolved.save()
    return update


class TimelineTests(TestCase):
    def test_full_lineage_renders_in_order_with_types_and_timestamps(self):
        chain = create_event_chain(create_source_authority(), sent=timezone.now() - timedelta(hours=3))
        add_update(chain)
        add_update(chain, msg_type="Cancel", headline="Cancelled", offset_hours=2)

        response = self.client.get(reverse("alert_detail", args=[chain.pk]))

        content = response.content.decode()
        self.assertIn("alert-timeline", content)
        # all three entries, in sent order
        first = content.index(">Alert<")
        update = content.index(">Update<")
        cancel = content.index(">Cancel<")
        self.assertLess(first, update)
        self.assertLess(update, cancel)


class VersionPageTests(TestCase):
    def setUp(self):
        self.chain = create_event_chain(create_source_authority(), sent=timezone.now() - timedelta(hours=3))
        self.original = self.chain.latest_alert
        self.update = add_update(self.chain)

    def test_timeline_links_each_message_to_its_version_page(self):
        response = self.client.get(reverse("alert_detail", args=[self.chain.pk]))

        self.assertContains(response, reverse("alert_version", args=[self.chain.pk, self.original.pk]))

    def test_prior_message_renders_with_a_superseded_banner(self):
        response = self.client.get(reverse("alert_version", args=[self.chain.pk, self.original.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flooding expected along the coast")  # the original content
        self.assertContains(response, "superseded")
        self.assertContains(response, reverse("alert_detail", args=[self.chain.pk]))  # back to current

    def test_current_message_version_page_has_no_superseded_banner(self):
        response = self.client.get(reverse("alert_version", args=[self.chain.pk, self.update.pk]))

        self.assertNotContains(response, "superseded")

    def test_version_page_404s_for_a_message_outside_the_chain(self):
        stranger = create_event_chain(
            create_source_authority(name="Other Met", country="ug", sender_values=["o@x"])
        )

        response = self.client.get(reverse("alert_version", args=[self.chain.pk, stranger.latest_alert.pk]))

        self.assertEqual(response.status_code, 404)


class OpenGraphTests(TestCase):
    def test_detail_page_carries_og_and_twitter_meta(self):
        chain = create_event_chain(create_source_authority(name="Kenya Met"))

        response = self.client.get(reverse("alert_detail", args=[chain.pk]))

        content = response.content.decode()
        self.assertIn('property="og:title"', content)
        self.assertIn("Flooding expected along the coast", content)
        self.assertIn('property="og:description"', content)
        self.assertIn('name="twitter:card"', content)
        # description mentions severity + issuer so the unfurl is meaningful
        self.assertIn("Severe", content.split('property="og:description"')[1][:200])


class RelatedAlertsTests(TestCase):
    def test_recent_alerts_from_the_same_authority_are_listed_excluding_self(self):
        authority = create_source_authority(name="Kenya Met")
        chain = create_event_chain(authority)
        sibling = create_event_chain(authority, infos=[{"headline": "Cyclone approaching the coast"}])
        foreign = create_event_chain(
            create_source_authority(name="Other Met", country="ug", sender_values=["o@x"]),
            infos=[{"headline": "Unrelated dust storm"}],
        )

        response = self.client.get(reverse("alert_detail", args=[chain.pk]))

        self.assertContains(response, "Cyclone approaching the coast")
        self.assertContains(response, reverse("alert_detail", args=[sibling.pk]))
        self.assertNotContains(response, "Unrelated dust storm")
        self.assertIsNotNone(foreign)
        # the page must not list itself as related
        content = response.content.decode()
        related_section = content.split("More from")[1]
        self.assertNotIn(f'href="{reverse("alert_detail", args=[chain.pk])}"', related_section)
