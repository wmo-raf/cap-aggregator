"""MQTT consumer service — bridges Mosquitto to the Celery ingestion queue.

Runs as its own container (entrypoint mode `mqtt-consumer`).
Subscribes to `cap/in/#` with QoS 1; each message
is handed to `ingest_raw_message` on the `capagg-ingestion` queue, so the
Celery broker (Redis) provides durability once the MQTT PUBACK is sent.

Expected payload (published by cap-composer, see cap/mqtt/publish.py there):

    {"data": "<base64 CAP XML>", "filename": "Actual_20260706T120000_slug.xml"}

Raw (non-JSON) CAP XML payloads are also accepted for non-composer publishers.
"""

import base64
import json
import logging
import signal

import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the MQTT → Celery ingestion consumer"

    def handle(self, *args, **options):
        from capaggregator.ingestion.tasks import ingest_raw_message

        def on_connect(client, userdata, flags, reason_code, properties=None):
            if reason_code == 0:
                client.subscribe(settings.MQTT_IN_TOPIC, qos=1)
                logger.info("Subscribed to %s", settings.MQTT_IN_TOPIC)
            else:
                logger.error("MQTT connect failed: %s", reason_code)

        def on_message(client, userdata, msg):
            try:
                xml_bytes = extract_xml(msg.payload)
            except Exception:
                logger.exception("Undecodable payload on %s — enqueueing raw for quarantine", msg.topic)
                xml_bytes = msg.payload

            ingest_raw_message.delay(
                transport="mqtt",
                topic=msg.topic,
                xml=xml_bytes.decode("utf-8", errors="replace"),
            )

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="capagg-consumer", clean_session=False)
        client.username_pw_set(settings.MQTT_CONSUMER_USERNAME, settings.MQTT_CONSUMER_PASSWORD)
        client.on_connect = on_connect
        client.on_message = on_message
        client.reconnect_delay_set(min_delay=1, max_delay=60)

        def shutdown(signum, frame):
            logger.info("Shutting down MQTT consumer")
            client.disconnect()

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)

        client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=60)
        self.stdout.write(f"MQTT consumer connected to {settings.MQTT_HOST}:{settings.MQTT_PORT}")
        client.loop_forever(retry_first_connection=True)


def extract_xml(payload: bytes) -> bytes:
    """cap-composer wraps the XML as {'data': b64, 'filename': ...}; accept raw XML too."""
    stripped = payload.lstrip()
    if stripped.startswith(b"{"):
        body = json.loads(payload)
        return base64.b64decode(body["data"])
    return payload
