"""Shared object factories for the test suite (reused across Phase B slices)."""

import uuid

from capaggregator.sources.models import SourceAuthority

from .cap_samples import DEFAULT_SENDER


def create_source_authority(
    name="Test Authority",
    country="ke",
    sender_values=None,
    feed_url="https://example.test/rss.xml",
    **kwargs,
):
    return SourceAuthority.objects.create(
        name=name,
        country=country,
        sender_values=sender_values if sender_values is not None else [DEFAULT_SENDER],
        feed_url=feed_url,
        **kwargs,
    )


def create_raw_message(authority, state="stored", transport="poll", received_at=None):
    """A RawMessage in a given state; received_at (auto_now_add) backdated if given."""
    from capaggregator.ingestion.models import RawMessage

    raw = RawMessage.objects.create(
        authority=authority, transport=transport, xml="<alert/>",
        sha256=uuid.uuid4().hex + uuid.uuid4().hex, state=state,
    )
    if received_at is not None:
        RawMessage.objects.filter(pk=raw.pk).update(received_at=received_at)
    return raw


def create_source_event(authority=None, ok=True, transport="poll", occurred_at=None):
    """A SourceEvent; occurred_at (auto_now_add) backdated if given."""
    from capaggregator.ingestion.models import SourceEvent

    event = SourceEvent.objects.create(authority=authority, transport=transport, ok=ok)
    if occurred_at is not None:
        SourceEvent.objects.filter(pk=event.pk).update(occurred_at=occurred_at)
    return event


def create_quarantined_message(authority=None, report=None, status="pending"):
    """A RawMessage + its QuarantinedMessage, without running the pipeline."""
    from capaggregator.ingestion.models import QuarantinedMessage, RawMessage

    if report is None:
        report = {"errors": [{"check": "sender", "message": "sender not registered"}], "warnings": []}
    raw = RawMessage.objects.create(
        authority=authority,
        transport="manual",
        xml="<alert/>",
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        state="quarantined",
    )
    return QuarantinedMessage.objects.create(raw_message=raw, report=report, status=status)


def create_cap_alert(
    authority,
    chain=None,
    identifier=None,
    msg_type="Alert",
    status="Actual",
    sent=None,
    xml=None,
    infos=None,
    references=None,
):
    """An immutable Alert with one AlertInfo per `infos` entry (dicts of AlertInfo
    field overrides; defaults to a single English 'Flood Warning' block)."""
    from django.utils import timezone

    from capaggregator.alerts.models import Alert, AlertInfo
    from capaggregator.ingestion.models import RawMessage

    sent = sent or timezone.now()
    identifier = identifier or f"urn:test:{uuid.uuid4()}"
    raw = RawMessage.objects.create(
        authority=authority, transport="poll", xml=xml or f"<alert><identifier>{identifier}</identifier></alert>",
        sha256=uuid.uuid4().hex + uuid.uuid4().hex, state="stored",
    )
    alert = Alert.objects.create(
        authority=authority, raw_message=raw, chain=chain, identifier=identifier,
        sender=DEFAULT_SENDER, sent=sent, msg_type=msg_type, status=status,
        scope="Public", references=references or [],
    )
    for info_kwargs in infos if infos is not None else [{}]:
        defaults = {
            "language": "en", "categories": ["Met"], "event": "Flood Warning",
            "urgency": "Immediate", "severity": "Severe", "certainty": "Likely",
            "effective": sent, "expires": sent + timezone.timedelta(hours=24),
            "headline": "Flooding expected along the coast",
            "description": "Heavy rainfall is expected.",
            "instruction": "Move to higher ground.",
        }
        defaults.update(info_kwargs)
        AlertInfo.objects.create(alert=alert, **defaults)
    return alert


def create_event_chain(authority=None, alert=None, is_cancelled=False, resolved_kwargs=None, **alert_kwargs):
    """An EventChain + its ResolvedAlert read model, denormalized from the alert's
    first info block (mirroring what the lineage resolver produces)."""
    from capaggregator.alerts.models import EventChain, ResolvedAlert

    authority = authority or create_source_authority()
    alert = alert or create_cap_alert(authority, **alert_kwargs)
    chain = EventChain.objects.create(
        authority=authority, first_alert=alert, latest_alert=alert, is_cancelled=is_cancelled,
    )
    alert.chain = chain
    alert.save(update_fields=["chain"])
    info = alert.infos.first()
    resolved_fields = {
        "authority": authority, "latest_alert": alert,
        "msg_type": alert.msg_type, "status": alert.status,
        "event": info.event, "categories": info.categories, "urgency": info.urgency,
        "severity": info.severity, "certainty": info.certainty,
        "languages": [i.language for i in alert.infos.all()],
        "headline": info.headline, "onset": info.onset,
        "effective": info.effective, "expires": info.expires,
        "is_cancelled": is_cancelled, "countries": [str(authority.country).lower()],
    }
    resolved_fields.update(resolved_kwargs or {})
    ResolvedAlert.objects.create(chain=chain, **resolved_fields)
    return chain
