"""Ingestion health computation.

Pure functions that turn RawMessage + SourceEvent history into the per-authority,
per-day status matrix the health dashboard renders. No rollup table, no cache —
two grouped aggregates over indexed columns, precedence applied in Python.
"""

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone


def mqtt_consumer_connected() -> bool:
    """Newest MQTT-consumer connectivity event (transport=mqtt, no authority):
    ok=True is a connect, ok=False a disconnect. Assumed connected until proven
    otherwise (no events yet)."""
    from .models import SourceEvent

    latest = (
        SourceEvent.objects.filter(transport="mqtt", authority__isnull=True)
        .order_by("-occurred_at", "-id").first()
    )
    return latest.ok if latest is not None else True


def _new_signal():
    return {"states": set(), "poll_ok": False, "poll_fail": False,
            "counts": {"stored": 0, "duplicate": 0, "quarantined": 0, "polls_ok": 0, "polls_failed": 0}}


def _status(signal) -> str:
    """Collapse a day's signals into a colour, worst-first."""
    if signal is None:
        return "gray"
    if signal["poll_fail"]:
        return "red"
    if signal["states"] & {"quarantined", "failed"}:
        return "orange"
    if signal["states"] & {"stored", "duplicate"}:
        return "green"
    if signal["poll_ok"]:
        return "alive"
    return "gray"


def build_health_matrix(*, days: int = 30, now=None, authority_id: int | None = None) -> dict:
    """Return {"days": [ISO dates], "authorities": [{id, name, country, statuses, detail_url}]}.

    One status per UTC day per active authority, worst-first ordered.
    """
    from capaggregator.sources.models import SourceAuthority

    from .models import RawMessage, SourceEvent

    now = now or timezone.now()
    today = now.date()
    day_list = [today - timedelta(days=n) for n in range(days - 1, -1, -1)]
    window_start = day_list[0]

    authorities = SourceAuthority.objects.filter(active=True)
    if authority_id is not None:
        authorities = authorities.filter(id=authority_id)
    authorities = list(authorities.order_by("name"))
    auth_ids = [a.id for a in authorities]

    signals = defaultdict(_new_signal)

    messages = (
        RawMessage.objects.filter(authority_id__in=auth_ids, received_at__date__gte=window_start)
        .annotate(day=TruncDate("received_at")).values("authority_id", "day", "state").annotate(n=Count("id"))
    )
    for row in messages:
        signal = signals[(row["authority_id"], row["day"])]
        signal["states"].add(row["state"])
        if row["state"] in signal["counts"]:
            signal["counts"][row["state"]] += row["n"]

    events = (
        SourceEvent.objects.filter(transport="poll", authority_id__in=auth_ids, occurred_at__date__gte=window_start)
        .annotate(day=TruncDate("occurred_at")).values("authority_id", "day", "ok").annotate(n=Count("id"))
    )
    for row in events:
        signal = signals[(row["authority_id"], row["day"])]
        signal["poll_ok" if row["ok"] else "poll_fail"] = True
        signal["counts"]["polls_ok" if row["ok"] else "polls_failed"] += row["n"]

    single = authority_id is not None
    rows = []
    for authority in authorities:
        entry = {
            "id": authority.id,
            "name": authority.name,
            "country": authority.country,
            "statuses": [_status(signals.get((authority.id, day))) for day in day_list],
            "detail_url": f"/admin/capagg-sources/{authority.id}/monitor/",
        }
        if single:
            entry["counts"] = [dict(signals[(authority.id, day)]["counts"]) for day in day_list]
        rows.append(entry)

    rows.sort(key=_worst_first_key)
    return {"days": [d.isoformat() for d in day_list], "authorities": rows}


def _worst_first_key(row):
    """Red authorities first (most-recent-red first), then orange, then alphabetical.
    day_list is oldest→newest, so a higher index is a more recent day."""
    statuses = row["statuses"]
    red = [i for i, s in enumerate(statuses) if s == "red"]
    orange = [i for i, s in enumerate(statuses) if s == "orange"]
    if red:
        return (0, -max(red), "")
    if orange:
        return (1, -max(orange), "")
    return (2, 0, row["name"])
