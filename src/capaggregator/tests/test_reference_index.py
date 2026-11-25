"""Our admin registers must stay out of Wagtail's reference index (#137).

Registering a snippet viewset calls `ReferenceIndex.register_model`, so every
save of a register row with a foreign key wrote index rows — one per FK, per
row. On the ingestion hot path (a SourceEvent per poll, a RawMessage and Alert
per message) that grew `wagtailcore_referenceindex` to 2 GB in production, the
largest table in the database, to back a "usage" view nobody needs on
immutable, high-volume registers."""

from django.test import TestCase

from wagtail.models import ReferenceIndex
from wagtail.snippets.models import get_snippet_models

from capaggregator.tests.factories import (
    create_alert_defect,
    create_raw_message,
    create_source_authority,
    create_source_event,
)


class ReferenceIndexTests(TestCase):
    def test_no_capagg_register_is_reference_indexed(self):
        ours = [m for m in get_snippet_models() if m._meta.app_label.startswith("capagg_")]
        self.assertTrue(ours, "expected our snippet registers to be loaded")
        indexed = [m._meta.label for m in ours if ReferenceIndex.is_indexed(m)]
        self.assertEqual(indexed, [])

    def test_ingesting_writes_no_reference_index_rows(self):
        authority = create_source_authority(name="Kenya Met")
        create_source_event(authority)
        create_raw_message(authority)
        create_alert_defect(authority=authority)  # also creates the Alert it hangs off

        self.assertFalse(ReferenceIndex.objects.exists())
