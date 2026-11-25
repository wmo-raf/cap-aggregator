"""Operator alerting: email ADMINS when feed polling stops succeeding.

The homepage "Last check" line is the only other place a polling outage shows,
and in prod it went unread for 16 days while the polling worker was wedged.
This turns the same signal (newest successful poll vs OPERATIONAL_WINDOW) into
email, debounced so an outage produces three kinds of mail and no more:

- one **stale** alert when polling first goes stale,
- a **reminder** every REMINDER_INTERVAL while it stays stale,
- one **recovered** mail when a poll succeeds again.

The last notified state lives in the Django cache (Redis) so worker restarts do
not re-alert. Called every 5 minutes by the `check_polling_freshness` task.

Known limit: this runs on our own Celery/Redis/DB, so an outage of those (or of
the host) cannot alert through it.
"""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.core.mail import mail_admins
from django.utils import timezone

from .health import OPERATIONAL_WINDOW, last_successful_poll

logger = logging.getLogger(__name__)

STATE_CACHE_KEY = "capagg-polling-freshness"
REMINDER_INTERVAL = timedelta(hours=24)

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
    previous = cache.get(STATE_CACHE_KEY) or {}

    if is_stale:
        if previous.get("state") != STALE:
            kind = "stale"
        elif now - previous["notified_at"] >= REMINDER_INTERVAL:
            kind = "reminder"
        else:
            return None
        subject, body = _stale_message(now, last_ok, reminder=kind == "reminder")
        if not _send(subject, body):
            return None
        cache.set(STATE_CACHE_KEY, {"state": STALE, "notified_at": now}, timeout=None)
        return kind

    if previous.get("state") == STALE:
        subject, body = _recovered_message(last_ok)
        if not _send(subject, body):
            return None
        cache.set(STATE_CACHE_KEY, {"state": HEALTHY, "notified_at": now}, timeout=None)
        return "recovered"

    if previous.get("state") != HEALTHY:
        cache.set(STATE_CACHE_KEY, {"state": HEALTHY, "notified_at": None}, timeout=None)
    return None


def _send(subject, body) -> bool:
    try:
        mail_admins(subject, body, fail_silently=False)
    except Exception:
        logger.exception("Polling-freshness alert could not be sent: %s", subject)
        return False
    logger.warning("Polling-freshness alert sent: %s", subject)
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


def _ago(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 120:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    return f"{hours // 24} days"
