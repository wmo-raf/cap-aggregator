"""CAP <expires> is optional and validators only warn when it's missing, so a
NULL expiry can reach the resolver. The resolved read model must never carry
one: the tile SQL would render such an alert forever while the homepage's
`expires > now` queries silently drop it — the same alert both permanently on
the map and absent from the counts. The resolver assigns a default active
window instead."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase

from capaggregator.alerts.lineage import DEFAULT_ACTIVE_WINDOW, resolve
from capaggregator.alerts.models import Alert
from capaggregator.ingestion.tasks import ingest_raw_message
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_source_authority


class ResolverDefaultExpiryTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority()

    def resolved_for(self, xml):
        with patch("capaggregator.alerts.tasks.resolve_lineage.delay"):
            stored = ingest_raw_message(transport="manual", xml=xml, authority_id=self.authority.id)
        alert = Alert.objects.get(id=stored["alert_id"])
        return resolve(alert).resolved

    def test_missing_expires_gets_a_default_active_window(self):
        resolved = self.resolved_for(cap_alert_xml(expires=None))

        self.assertIsNotNone(resolved.expires)
        self.assertEqual(resolved.expires, resolved.effective + DEFAULT_ACTIVE_WINDOW)
        self.assertEqual(DEFAULT_ACTIVE_WINDOW, timedelta(hours=24))

    def test_an_explicit_expires_is_kept_verbatim(self):
        resolved = self.resolved_for(cap_alert_xml())

        self.assertEqual(resolved.expires.isoformat(), "2026-07-08T12:00:00+00:00")
