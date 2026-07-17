"""Ingestion Celery tasks. Conventions: bind=True, acks_late=True, late imports
inside task bodies, max_retries=0 on the main task with recovery via the
sweep_unprocessed periodic task.

Transport resolution (docs/design.md §1):
  All transports (MQTT preferred, webhook optional, feed poll mandatory) feed
  the same task. Content is stored FIRST-WINS — CAP messages are immutable, so
  whichever transport arrives first delivers the content; every arrival
  (including duplicates) is logged as a DeliveryReceipt for health telemetry.

  Dedup is two-layer:
    1. sha256 of the exact bytes (fast path — same transport redelivery)
    2. CAP identity triple (sender, identifier, sent) after parse — catches the
       same alert with byte differences across transports (stylesheet PI,
       signed vs unsigned serialization, whitespace).

The validate→store→resolve stages live in run_pipeline() so they can be reused
outside the task — e.g. the quarantine re-validation and backfill task-ferry jobs.
"""

import hashlib
import logging

from celery import shared_task
from celery_singleton import Singleton

logger = logging.getLogger(__name__)

# Concurrent CAP XML fetches per poll — bounds our politeness toward one source
CAP_FETCH_POOL_SIZE = 10


def run_pipeline(raw, transport: str | None = None, authority=None) -> dict:
    """Identity-dedup → validate → quarantine | parse & store → receipt →
    lineage, for an already-persisted RawMessage.

    Shared by ingest_raw_message and the task-ferry jobs (backfill,
    quarantine re-validation). Returns {"state": ..., ...}.
    """
    from django.db import IntegrityError, transaction

    from capaggregator.alerts.models import Alert
    from capaggregator.alerts.parser import parse_and_store, parse_identity

    from .models import DeliveryReceipt, QuarantinedMessage
    from .validators import run_validators

    transport = transport or raw.transport
    authority = authority if authority is not None else raw.authority

    # --- Dedup layer 2: same CAP identity triple with different bytes ---
    identity = parse_identity(raw.xml)
    if identity is not None:
        existing = Alert.objects.filter(
            sender=identity["sender"], identifier=identity["identifier"], sent=identity["sent"],
        ).first()
        if existing is not None:
            raw.state = "duplicate"
            raw.save()
            DeliveryReceipt.objects.create(authority=authority, transport=transport,
                                           alert=existing, raw_message=raw, was_first=False)
            logger.info("Duplicate identity %s via %s (bytes differ) — receipt recorded",
                        identity["identifier"], transport)
            return {"state": "duplicate", "raw_id": raw.id, "alert_id": existing.id}

    # --- Validate ---
    report = run_validators(raw)

    if report.has_errors:
        raw.state = "quarantined"
        raw.save()
        QuarantinedMessage.objects.create(raw_message=raw, report=report.as_dict())
        logger.warning("Message %s quarantined: %s", raw.sha256[:12], report.error_summary())
        return {"state": "quarantined", "raw_id": raw.id}

    raw.state = "validated"
    raw.save()

    # --- Store (unique constraint on the triple is the concurrency backstop) ---
    try:
        with transaction.atomic():
            alert = parse_and_store(raw, warnings=report.warnings)
    except IntegrityError:
        # Race: another transport stored the same triple between our check and now
        raw.state = "duplicate"
        raw.save()
        existing = None
        if identity:
            existing = Alert.objects.filter(
                sender=identity["sender"], identifier=identity["identifier"], sent=identity["sent"],
            ).first()
        DeliveryReceipt.objects.create(authority=authority, transport=transport,
                                       alert=existing, raw_message=raw, was_first=False)
        return {"state": "duplicate", "raw_id": raw.id}

    raw.state = "stored"
    raw.sent_at = alert.sent
    raw.save()

    DeliveryReceipt.objects.create(authority=authority, transport=transport,
                                   alert=alert, raw_message=raw, was_first=True)

    # Lineage resolution + fan-out (SSE, re-publication, metrics)
    from capaggregator.alerts.tasks import resolve_lineage

    resolve_lineage.delay(alert.id)

    return {"state": "stored", "raw_id": raw.id, "alert_id": alert.id}


@shared_task(bind=True, acks_late=True, max_retries=0)
def ingest_raw_message(self, transport: str, xml: str, topic: str = "", authority_id: int | None = None):
    """Single entry point for all transports (MQTT, webhook, poll, manual)."""
    from capaggregator.sources.models import SourceAuthority

    from .models import DeliveryReceipt, RawMessage

    sha256 = hashlib.sha256(xml.encode()).hexdigest()

    raw, created = RawMessage.objects.get_or_create(
        sha256=sha256,
        defaults={"transport": transport, "topic": topic, "xml": xml, "authority_id": authority_id},
    )

    # Resolve authority from topic when not passed explicitly (MQTT path):
    # topic layout is cap/in/{country}/{authority_slug}
    authority = raw.authority
    if authority is None and topic.startswith("cap/in/"):
        parts = topic.split("/")
        if len(parts) >= 4:
            authority = SourceAuthority.objects.filter(slug=parts[3], country=parts[2].upper()).first()
            raw.authority = authority

    # --- Dedup layer 1: exact bytes already seen ---
    if not created:
        existing_alert = raw.alerts.first()
        DeliveryReceipt.objects.create(authority=authority, transport=transport,
                                       alert=existing_alert, raw_message=raw, was_first=False)
        logger.info("Duplicate bytes %s via %s — receipt recorded", sha256[:12], transport)
        return {"state": "duplicate", "raw_id": raw.id}

    return run_pipeline(raw, transport=transport, authority=authority)


@shared_task(bind=True, acks_late=True)
def sweep_unprocessed(self):
    """Periodic recovery: re-run messages stuck in 'received' (worker died mid-task)."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import RawMessage

    cutoff = timezone.now() - timedelta(minutes=15)
    stuck = RawMessage.objects.filter(state="received", received_at__lt=cutoff)
    for raw in stuck.iterator():
        logger.info("Sweeping stuck raw message %s", raw.id)
        ingest_raw_message.delay(transport=raw.transport, xml=raw.xml, topic=raw.topic,
                                 authority_id=raw.authority_id)


@shared_task(bind=True, acks_late=True)
def purge_old_source_events(self):
    """Daily retention: delete transport telemetry older than 90 days so the
    SourceEvent table stays bounded (the dashboard only ever reads 30 days)."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import SourceEvent

    cutoff = timezone.now() - timedelta(days=90)
    deleted, _ = SourceEvent.objects.filter(occurred_at__lt=cutoff).delete()
    if deleted:
        logger.info("Purged %s SourceEvent rows older than 90 days", deleted)


@shared_task(base=Singleton, lock_expiry=120, bind=True, acks_late=True)
def poll_all_feeds(self):
    """Celery-beat entry point: fan out one poll_feed per authority that is due.

    Singleton: a beat tick firing while the previous scan is still running is a
    no-op (lock_expiry backstops a killed worker; the scan itself takes seconds).

    Adaptive interval per authority:
      - push transport configured AND healthy → feed_reconcile_interval_minutes
      - otherwise → feed_poll_interval_minutes (fast)
    'Healthy' = a push (mqtt/webhook) receipt within the last reconcile window.
    """
    from datetime import timedelta

    from django.utils import timezone

    from capaggregator.sources.models import SourceAuthority

    from .models import DeliveryReceipt

    now = timezone.now()
    for authority in SourceAuthority.objects.filter(active=True).exclude(feed_url=""):
        window = timedelta(minutes=authority.feed_reconcile_interval_minutes)
        push_healthy = (
            authority.has_push_transport
            and DeliveryReceipt.objects.filter(
                authority=authority, transport__in=["mqtt", "webhook"],
                received_at__gte=now - window,
            ).exists()
        )
        if push_healthy:
            interval = authority.feed_reconcile_interval_minutes
        else:
            # Failing feeds back off exponentially (1→2→4… min) up to the
            # reconcile interval; one success resets the counter to 0
            interval = min(
                authority.feed_reconcile_interval_minutes,
                authority.feed_poll_interval_minutes * 2**authority.feed_consecutive_failures,
            )

        # feed_last_polled is stamped at poll END; half a beat tick of slack
        # keeps a nonzero poll duration from pushing the next due moment just
        # past the next tick (which would double the effective cadence).
        slack = timedelta(seconds=30)
        due = (authority.feed_last_polled is None
               or authority.feed_last_polled <= now - (timedelta(minutes=interval) - slack))
        if due:
            poll_feed.delay(authority.id)


@shared_task(base=Singleton, lock_expiry=300, bind=True, acks_late=True, max_retries=0)
def poll_feed(self, authority_id: int):
    """Poll one authority's CAP feed (mandatory baseline transport).

    Conditional GET (ETag/Last-Modified); skips entries whose CAP identifier is
    already stored (cheap guard — full dedup still happens in ingest_raw_message).

    Singleton per authority_id: the dispatcher re-scans every 60s while
    feed_last_polled is stamped at poll END, so a poll slower than a tick would
    otherwise get a concurrent duplicate racing the conditional-GET state
    (lock_expiry backstops a killed worker)."""
    import requests
    from django.utils import timezone

    from capaggregator.alerts.models import Alert
    from capaggregator.sources.feeds import fetch_cap_xml, fetch_feed
    from capaggregator.sources.models import SourceAuthority

    authority = SourceAuthority.objects.filter(id=authority_id, active=True).first()
    if authority is None or not authority.feed_url:
        return

    # One keep-alive session per poll cycle: the feed + every CAP XML fetch
    # share connections instead of re-handshaking per request
    session = requests.Session()
    try:
        try:
            entries, changed = fetch_feed(authority, session=session)
        except Exception as ex:
            logger.warning("Feed poll failed for %s: %s", authority.slug, ex)
            authority.feed_last_polled = timezone.now()
            authority.feed_consecutive_failures += 1
            authority.save(update_fields=["feed_last_polled", "feed_consecutive_failures"])

            from .models import SourceEvent

            SourceEvent.objects.create(authority=authority, transport="poll", ok=False, error=str(ex))
            return

        to_fetch = []
        for entry in entries:
            entry_id = entry["id"]
            cap_url = entry["cap_url"]
            if not cap_url:
                continue
            # Cheap guard: feed entry ids from cap-composer equal the CAP identifier.
            # A DeliveryReceipt for already-seen alerts is still valuable, but fetching
            # every XML every poll is not — only fetch when the identifier is unknown.
            if entry_id and Alert.objects.filter(authority=authority, identifier=entry_id).exists():
                continue
            to_fetch.append(cap_url)

        fetched = 0
        if to_fetch:
            # Backlogs (onboarding, post-outage) would cost entries x round-trip
            # serially; a bounded greenlet pool overlaps the fetches while staying
            # polite to the source server. Lazy import: only the gevent polling
            # worker runs this task — gevent must never load in pipeline workers.
            from gevent.pool import Pool

            def fetch_one(cap_url):
                try:
                    return fetch_cap_xml(cap_url, session=session)
                except Exception as ex:
                    logger.warning("Failed to fetch CAP XML %s: %s", cap_url, ex)
                    return None

            for xml in Pool(CAP_FETCH_POOL_SIZE).imap_unordered(fetch_one, to_fetch):
                if xml is None:
                    continue
                ingest_raw_message.delay(transport="poll", xml=xml, authority_id=authority.id)
                fetched += 1
    finally:
        session.close()

    authority.feed_last_polled = timezone.now()
    authority.feed_consecutive_failures = 0
    authority.save(update_fields=["feed_etag", "feed_last_modified", "feed_type_detected",
                                  "feed_last_polled", "feed_consecutive_failures"])

    from .models import SourceEvent

    SourceEvent.objects.create(authority=authority, transport="poll", ok=True, detail={"entries_fetched": fetched})
    if fetched:
        logger.info("Feed poll %s: %s new entries enqueued", authority.slug, fetched)
