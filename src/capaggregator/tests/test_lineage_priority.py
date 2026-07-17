"""A stored alert must surface in resolved state (tiles, search, live stream)
without queueing behind bulk work: lineage resolution publishes at the highest
broker priority while ordinary tasks ride the default tier.

Redis priority semantics are inverted vs AMQP: 0 is the HIGHEST priority (the
bare queue is consumed before its :N suffixed variants)."""

from django.test import SimpleTestCase

from capaggregator.alerts.tasks import resolve_lineage
from capaggregator.config.celery import app


class LineagePriorityTests(SimpleTestCase):
    def test_redis_broker_priorities_are_enabled(self):
        opts = app.conf.broker_transport_options
        self.assertEqual(opts.get("queue_order_strategy"), "priority")
        self.assertIn(0, opts.get("priority_steps", []))

    def test_resolve_lineage_publishes_at_the_highest_priority(self):
        self.assertEqual(resolve_lineage.priority, 0)

    def test_ordinary_tasks_ride_the_default_priority_tier(self):
        self.assertEqual(app.conf.task_default_priority, 5)
