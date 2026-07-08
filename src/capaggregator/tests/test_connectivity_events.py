"""Health dashboard 5/5: the remaining SourceEvent writers — webhook rejections and
MQTT consumer connect/disconnect — completing the telemetry the dashboard reads."""

from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse

from capaggregator.ingestion.models import SourceEvent
from capaggregator.tests.factories import create_source_authority


class WebhookEventTests(TestCase):
    def _url(self, token):
        return reverse("webhook_ingest", args=[token])

    def test_invalid_token_records_an_unattributed_rejection_and_403(self):
        response = self.client.post(self._url("bogus-token"), data="<alert/>", content_type="application/xml")

        self.assertEqual(response.status_code, 403)
        event = SourceEvent.objects.get()
        self.assertEqual(event.transport, "webhook")
        self.assertFalse(event.ok)
        self.assertIsNone(event.authority_id)

    def test_valid_token_empty_body_records_an_attributed_rejection_and_400(self):
        authority = create_source_authority(name="Kenya Met")

        response = self.client.post(self._url(authority.webhook_token), data="   ", content_type="application/xml")

        self.assertEqual(response.status_code, 400)
        event = SourceEvent.objects.get()
        self.assertFalse(event.ok)
        self.assertEqual(event.authority_id, authority.id)

    @patch("capaggregator.ingestion.tasks.ingest_raw_message")
    def test_successful_webhook_records_no_event(self, _ingest):
        authority = create_source_authority(name="Kenya Met")

        response = self.client.post(
            self._url(authority.webhook_token), data="<alert/>", content_type="application/xml"
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(SourceEvent.objects.count(), 0)


class MqttConnectivityTests(TestCase):
    def test_on_connect_success_records_a_connect_event(self):
        from capaggregator.ingestion.management.commands.mqtt_consumer import on_connect

        on_connect(Mock(), None, None, 0)

        event = SourceEvent.objects.get()
        self.assertEqual(event.transport, "mqtt")
        self.assertIsNone(event.authority_id)
        self.assertTrue(event.ok)

    def test_on_connect_failure_records_a_failed_event(self):
        from capaggregator.ingestion.management.commands.mqtt_consumer import on_connect

        on_connect(Mock(), None, None, 5)

        self.assertFalse(SourceEvent.objects.get().ok)

    def test_on_disconnect_records_a_disconnect_event(self):
        from capaggregator.ingestion.management.commands.mqtt_consumer import on_disconnect

        on_disconnect(Mock(), None)

        event = SourceEvent.objects.get()
        self.assertEqual(event.transport, "mqtt")
        self.assertIsNone(event.authority_id)
        self.assertFalse(event.ok)

    def test_connectivity_callbacks_drive_the_connected_flag(self):
        from capaggregator.ingestion.health import mqtt_consumer_connected
        from capaggregator.ingestion.management.commands.mqtt_consumer import on_connect, on_disconnect

        self.assertTrue(mqtt_consumer_connected())  # no events yet

        on_disconnect(Mock(), None)
        self.assertFalse(mqtt_consumer_connected())

        on_connect(Mock(), None, None, 0)
        self.assertTrue(mqtt_consumer_connected())
