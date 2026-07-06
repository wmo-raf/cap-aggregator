import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, acks_late=True, max_retries=0)
def resolve_lineage(self, alert_id: int):
    """Attach an ingested alert to its event chain and refresh resolved state,
    then fan out (SSE live-mode event, re-publication, metrics)."""
    from .lineage import resolve
    from .models import Alert

    alert = Alert.objects.filter(id=alert_id).first()
    if alert is None:
        logger.warning("Alert %s not found for lineage resolution", alert_id)
        return

    chain = resolve(alert)
    logger.info("Alert %s resolved into chain %s", alert_id, chain.pk)

    # Fan-out: publish event for SSE live mode (Redis pub/sub)
    _publish_live_event(alert, chain)

    # TODO: re-publication tasks (filtered ATOM cache bust, MQTT cap/out/*, webhooks)
    # TODO: metrics row (ingest latency = raw.received_at - alert.sent)


def _publish_live_event(alert, chain):
    import json

    import redis
    from django.conf import settings

    try:
        r = redis.from_url(settings.REDIS_URL)
        r.publish("capagg:alerts", json.dumps({
            "alert_id": alert.id,
            "chain_id": chain.pk,
            "msg_type": alert.msg_type,
        }))
    except Exception:
        logger.exception("Failed to publish live event")
