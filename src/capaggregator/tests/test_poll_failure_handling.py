"""A DB outage mid-poll must fail the poll task, not the worker.

Prod, 2026-11-08: Postgres restarted under a running poll_feed. The task raised
OperationalError, then Celery's failure handler tried to store that failure in
the django-db result backend over the same dead connection and raised again.
That second exception escapes the tracer, which in the gevent pool kills the
greenlet without completing the request: the message stays unacked, and once
every prefetch slot was held this way the polling worker stopped consuming for
16 days while still reporting itself alive.

Poll tasks therefore never store results (ignore_result) and carry a hard
time_limit for genuinely stalled I/O."""

from unittest.mock import patch

from celery.app.trace import build_tracer
from django.db.utils import OperationalError
from django.test import SimpleTestCase

from capaggregator.ingestion import tasks


class PollTaskOptionsTests(SimpleTestCase):
    def test_poll_tasks_never_store_results(self):
        self.assertTrue(tasks.poll_feed.ignore_result)
        self.assertTrue(tasks.poll_all_feeds.ignore_result)

    def test_poll_tasks_have_hard_time_limits(self):
        self.assertEqual(tasks.poll_feed.time_limit, 90)
        self.assertEqual(tasks.poll_all_feeds.time_limit, 60)


class DbOutageDuringPollTests(SimpleTestCase):
    """Drive Celery's real tracer the way a worker does, with the task body and
    the result backend both failing as they did when the DB went away."""

    def trace(self, task):
        dead = OperationalError("the connection is closed")
        with patch.object(task, "run", side_effect=dead), \
                patch.object(task.backend, "store_result", side_effect=dead):
            tracer = build_tracer(task.name, task, app=task.app, eager=False, propagate=False)
            return tracer("task-id", (1,), {}, {"delivery_info": {}})

    def test_poll_feed_failure_does_not_escape_the_tracer(self):
        result = self.trace(tasks.poll_feed)  # returning at all = the request completes

        self.assertEqual(result.info.state, "FAILURE")
        self.assertIsInstance(result.info.retval, OperationalError)

    def test_a_task_that_stores_results_would_escape_the_tracer(self):
        """Control: with results stored, the same failure escapes (the prod bug)."""
        with patch.object(tasks.poll_feed, "ignore_result", False):
            with self.assertRaises(OperationalError):
                self.trace(tasks.poll_feed)
