"""Operator alerting: email ADMINS when the ingestion pipeline stops moving.

Two independent checks, each run every 5 minutes by its own beat task:

- **polling freshness** — no feed poll has succeeded within OPERATIONAL_WINDOW.
  The homepage "Last check" line is the only other place this shows, and in
  prod it went unread for 16 days while the polling worker was wedged.
- **ingestion backlog** — fetched messages are not being processed. Polls keep
  succeeding while the capagg-ingestion worker is dead, so the freshness check
  cannot see this. Two signals, either one alerts:
  - work is queued on capagg-ingestion but the pipeline has written nothing
    (no RawMessage, no DeliveryReceipt) for STALL_AFTER. A dead or wedged worker
    leaves no other trace: RawMessage rows are only created by the worker.
  - work started and stuck: RawMessages in a non-terminal state, or stored
    alerts never lineage-resolved, for longer than STALL_AFTER.

Each is debounced so an outage produces three kinds of mail and no more:

- one **stale** alert when the problem first appears,
- a **reminder** every REMINDER_INTERVAL while it lasts,
- one **recovered** mail when it clears.

The last notified state lives in the Django cache (Redis), one key per check,
so worker restarts do not re-alert. The check tasks route to capagg-default so
they keep running when the workers they watch are down.

Known limit: this runs on our own Celery/Redis/DB, so an outage of those (or of
the host) cannot alert through it.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.core.cache import cache
from django.core.mail import mail_admins
from django.utils import timezone

from .health import OPERATIONAL_WINDOW, last_successful_poll

logger = logging.getLogger(__name__)

STATE_CACHE_KEY = "capagg-polling-freshness"
BACKLOG_CACHE_KEY = "capagg-ingestion-backlog"
REMINDER_INTERVAL = timedelta(hours=24)

# Unprocessed this long = stalled. Ingest autoretry gives up within ~3 min and
# sweep_unprocessed re-enqueues unfinished work every 5 min, so work still
# unfinished after 15 min has been through at least two sweeps and nobody is
# consuming it (or it fails every attempt).
STALL_AFTER = timedelta(minutes=15)
NON_TERMINAL_STATES = ("received", "validated")

STALE = "stale"
HEALTHY = "healthy"


def check_polling_freshness(now=None) -> str | None:
    """Compare polling freshness with the last notified state and send at most
    one email. Returns the kind of mail sent ("stale", "reminder", "recovered")
    or None. A send failure leaves the stored state unchanged, so the next run
    retries the same mail."""
    from capaggregator.sources.models import SourceAuthority

    now = now or timezone.now()
    first_feed_added = (
        SourceAuthority.objects.filter(active=True).exclude(feed_url="")
        .order_by("created").values_list("created", flat=True).first()
    )
    if first_feed_added is None:
        return None  # nothing is meant to be polled

    # Never polled successfully: stale only once a feed has existed for a full
    # window, so a fresh deploy is not alerted before its first poll runs
    last_ok = last_successful_poll()
    reference = last_ok or first_feed_added
    is_stale = now - reference > OPERATIONAL_WINDOW

    return _notify(
        STATE_CACHE_KEY, now,
        stale_message=(lambda reminder: _stale_message(now, last_ok, reminder)) if is_stale else None,
        recovered_message=lambda: _recovered_message(last_ok),
    )


def check_ingestion_backlog(now=None) -> str | None:
    """Alert when fetched messages stop being processed (see module docstring).
    Same return values and retry-on-send-failure as check_polling_freshness."""
    now = now or timezone.now()
    backlog = _ingestion_backlog(now - STALL_AFTER)

    return _notify(
        BACKLOG_CACHE_KEY, now,
        stale_message=(lambda reminder: _backlog_message(now, backlog, reminder)) if backlog.stalled else None,
        recovered_message=_backlog_recovered_message,
    )


def _notify(cache_key, now, stale_message, recovered_message) -> str | None:
    """The debounce shared by every check. `stale_message` is None while healthy,
    else a callable(reminder) -> (subject, body); `recovered_message` is a
    callable() -> (subject, body). Sends at most one mail and records it under
    `cache_key`; a failed send records nothing, so the next run retries it."""
    previous = cache.get(cache_key) or {}

    if stale_message is not None:
        if previous.get("state") != STALE:
            kind = "stale"
        elif now - previous["notified_at"] >= REMINDER_INTERVAL:
            kind = "reminder"
        else:
            return None
        if not _send(*stale_message(kind == "reminder")):
            return None
        cache.set(cache_key, {"state": STALE, "notified_at": now}, timeout=None)
        return kind

    if previous.get("state") == STALE:
        if not _send(*recovered_message()):
            return None
        cache.set(cache_key, {"state": HEALTHY, "notified_at": now}, timeout=None)
        return "recovered"

    if previous.get("state") != HEALTHY:
        cache.set(cache_key, {"state": HEALTHY, "notified_at": None}, timeout=None)
    return None


def _send(subject, body) -> bool:
    try:
        mail_admins(subject, body, fail_silently=False)
    except Exception:
        logger.exception("Operator alert could not be sent: %s", subject)
        return False
    logger.warning("Operator alert sent: %s", subject)
    return True


def _stale_message(now, last_ok, reminder: bool):
    from .models import SourceEvent

    if last_ok is None:
        since = "No feed poll has ever succeeded."
        failures_since = now - REMINDER_INTERVAL
    else:
        since = f"Last successful feed poll: {last_ok:%Y-%m-%d %H:%M} UTC ({_ago(now - last_ok)} ago)."
        failures_since = last_ok

    failures = list(
        SourceEvent.objects.filter(transport="poll", ok=False, authority__isnull=False,
                                   occurred_at__gte=failures_since)
        .select_related("authority")
        .order_by("authority_id", "-occurred_at")
        .distinct("authority_id")
    )
    if failures:
        lines = [f"Latest poll error per feed since then ({len(failures)} feeds):", ""]
        for event in sorted(failures, key=lambda e: e.authority.name):
            lines.append(f"- {event.authority.name} ({event.occurred_at:%Y-%m-%d %H:%M} UTC): {event.error[:300]}")
        detail = "\n".join(lines)
    else:
        detail = (
            "No poll has even recorded a failure since then, so polls are not running at all.\n"
            "Check the capagg-worker-polling and capagg-beat containers (stuck or dead worker, "
            "paused beat schedule, broker or database outage)."
        )

    prefix = "Still stale" if reminder else "Stale"
    subject = f"{prefix}: no successful feed poll for {_ago(now - last_ok) if last_ok else 'ever'}"
    body = (
        f"Feed polling has not succeeded within the last {_ago(OPERATIONAL_WINDOW)}.\n\n"
        f"{since}\n\n{detail}\n\n"
        f"You will get a reminder every {_ago(REMINDER_INTERVAL)} while this lasts, "
        "and one email when polling recovers.\n"
    )
    return subject, body


def _recovered_message(last_ok):
    subject = "Recovered: feed polling is succeeding again"
    body = f"A feed poll succeeded at {last_ok:%Y-%m-%d %H:%M} UTC. Ingestion via polling has resumed.\n"
    return subject, body


@dataclass
class Backlog:
    """What the ingestion pipeline has left unfinished since `cutoff`."""

    # Tasks waiting on capagg-ingestion; counted only when the pipeline has also
    # written nothing since the cutoff (a backfill queues thousands legitimately)
    queued_unconsumed: int = 0
    last_progress: datetime | None = None
    stuck_messages: int = 0
    oldest_stuck_message: datetime | None = None
    stuck_message_ids: list[int] = field(default_factory=list)
    unresolved_alerts: int = 0
    oldest_unresolved_alert: datetime | None = None

    @property
    def stalled(self) -> bool:
        return bool(self.queued_unconsumed or self.stuck_messages or self.unresolved_alerts)


def _ingestion_backlog(cutoff) -> Backlog:
    from django.db.models import Count, Min

    from capaggregator.alerts.models import Alert

    from .models import RawMessage

    backlog = Backlog()

    queued = _ingestion_queue_depth()
    if queued:
        backlog.last_progress = _last_pipeline_write()
        if backlog.last_progress is None or backlog.last_progress < cutoff:
            backlog.queued_unconsumed = queued

    stuck = RawMessage.objects.filter(state__in=NON_TERMINAL_STATES, received_at__lt=cutoff)
    agg = stuck.aggregate(n=Count("id"), oldest=Min("received_at"))
    backlog.stuck_messages, backlog.oldest_stuck_message = agg["n"], agg["oldest"]
    if backlog.stuck_messages:
        backlog.stuck_message_ids = list(stuck.order_by("received_at").values_list("id", flat=True)[:10])

    agg = Alert.objects.filter(chain__isnull=True, created__lt=cutoff).aggregate(n=Count("id"), oldest=Min("created"))
    backlog.unresolved_alerts, backlog.oldest_unresolved_alert = agg["n"], agg["oldest"]
    return backlog


def _ingestion_queue_depth() -> int | None:
    """Tasks waiting on capagg-ingestion (all priority levels), or None when the
    broker cannot be read — an unreadable queue is not itself evidence of a stall."""
    from amqp.exceptions import ChannelError

    from capaggregator.config.celery import app

    try:
        with app.connection_for_read() as conn:
            return conn.default_channel.queue_declare("capagg-ingestion", passive=True).message_count
    except ChannelError as exc:
        # Redis deletes an emptied list, so kombu reports an empty queue as 404
        # (its virtual transport passes the code as a string)
        if str(exc.reply_code) == "404":
            return 0
        logger.warning("Could not read the capagg-ingestion queue depth", exc_info=True)
        return None
    except Exception:
        logger.warning("Could not read the capagg-ingestion queue depth", exc_info=True)
        return None


def _last_pipeline_write():
    """When the ingestion worker last wrote anything: the newest RawMessage (new
    bytes) or DeliveryReceipt (every arrival, duplicates included). Newest by id,
    which is indexed and monotonic with the timestamp; received_at is not indexed
    on its own."""
    from .models import DeliveryReceipt, RawMessage

    times = [
        model.objects.order_by("-id").values_list("received_at", flat=True).first()
        for model in (RawMessage, DeliveryReceipt)
    ]
    times = [t for t in times if t is not None]
    return max(times) if times else None


def _backlog_message(now, backlog: Backlog, reminder: bool):
    lines, parts, oldest = [], [], []

    if backlog.queued_unconsumed:
        since = (f"since {backlog.last_progress:%Y-%m-%d %H:%M} UTC ({_ago(now - backlog.last_progress)} ago)"
                 if backlog.last_progress else "ever")
        lines.append(
            f"- {_n(backlog.queued_unconsumed, 'queued task')} waiting on capagg-ingestion, and the pipeline "
            f"has written no message or delivery receipt {since}: nothing is consuming the queue."
        )
        parts.append(_n(backlog.queued_unconsumed, "queued task"))
        if backlog.last_progress:
            oldest.append(backlog.last_progress)
    if backlog.stuck_messages:
        lines.append(
            f"- {_n(backlog.stuck_messages, 'received message')} not processed (state received/validated), "
            f"oldest {backlog.oldest_stuck_message:%Y-%m-%d %H:%M} UTC. Oldest RawMessage ids: "
            + ", ".join(str(i) for i in backlog.stuck_message_ids)
        )
        parts.append(_n(backlog.stuck_messages, "message"))
        oldest.append(backlog.oldest_stuck_message)
    if backlog.unresolved_alerts:
        lines.append(
            f"- {_n(backlog.unresolved_alerts, 'stored alert')} not lineage-resolved, oldest "
            f"{backlog.oldest_unresolved_alert:%Y-%m-%d %H:%M} UTC. They are missing from the map, API and feeds."
        )
        parts.append(_n(backlog.unresolved_alerts, "unresolved alert"))
        oldest.append(backlog.oldest_unresolved_alert)

    prefix = "Still stalled" if reminder else "Stalled"
    age = f", oldest {_ago(now - min(oldest))} old" if oldest else ""
    subject = f"{prefix}: ingestion backlog of {' and '.join(parts)}{age}"
    body = (
        f"Work fetched by the aggregator has not been processed for over {_ago(STALL_AFTER)}.\n\n"
        + "\n".join(lines)
        + "\n\n"
        "sweep_unprocessed re-enqueues unfinished work every 5 min, so a backlog this old usually means "
        "nothing is consuming the capagg-ingestion queue: check the capagg-worker-ingestion container "
        "(dead, wedged, or crash-looping) and the broker. If the worker is otherwise processing, any "
        "listed message ids are probably failing on every attempt: search its logs for them.\n\n"
        f"You will get a reminder every {_ago(REMINDER_INTERVAL)} while this lasts, "
        "and one email when the backlog clears.\n"
    )
    return subject, body


def _backlog_recovered_message():
    subject = "Recovered: ingestion backlog cleared"
    body = "No received message or stored alert is waiting longer than expected. Ingestion is processing again.\n"
    return subject, body


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _ago(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 120:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    return f"{hours // 24} days"
