"""Feed polling must never contend with pipeline work: poll tasks ride the
dedicated capagg-polling queue (I/O-bound transport polling only), while
validate/parse/store/resolve stay on capagg-ingestion and everything else
falls through to capagg-default."""

from django.test import SimpleTestCase

from capaggregator.config.celery import app


def routed_queue(task_name: str) -> str:
    """Resolve a task name through the same router the broker uses."""
    return app.amqp.router.route({}, task_name)["queue"].name


class TaskRoutingTests(SimpleTestCase):
    def test_poll_tasks_route_to_the_polling_queue(self):
        self.assertEqual(routed_queue("capaggregator.ingestion.tasks.poll_all_feeds"), "capagg-polling")
        self.assertEqual(routed_queue("capaggregator.ingestion.tasks.poll_feed"), "capagg-polling")

    def test_pipeline_tasks_stay_on_the_ingestion_queue(self):
        self.assertEqual(routed_queue("capaggregator.ingestion.tasks.ingest_raw_message"), "capagg-ingestion")
        self.assertEqual(routed_queue("capaggregator.alerts.tasks.resolve_lineage"), "capagg-ingestion")

    def test_unrouted_tasks_fall_through_to_the_default_queue(self):
        self.assertEqual(routed_queue("capaggregator.somewhere.tasks.some_future_task"), "capagg-default")
