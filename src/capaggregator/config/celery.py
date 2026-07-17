import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "capaggregator.config.settings.dev")

app = Celery("capaggregator")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Queue conventions:
#   capagg-polling   — I/O-bound transport polling only (feed fetches); consumed
#                      by the gevent polling worker — never route validation,
#                      parsing, storage, or lineage work here
#   capagg-ingestion — heavy pipeline work (validate/parse/resolve)
#   capagg-default   — everything else (notifications, re-publication, metrics)
# Exact-name entries must precede wildcards: Celery matches in declaration order.
app.conf.task_routes = {
    "capaggregator.ingestion.tasks.poll_all_feeds": {"queue": "capagg-polling"},
    "capaggregator.ingestion.tasks.poll_feed": {"queue": "capagg-polling"},
    "capaggregator.ingestion.tasks.*": {"queue": "capagg-ingestion"},
    "capaggregator.alerts.tasks.*": {"queue": "capagg-ingestion"},
    "*": {"queue": "capagg-default"},
}
app.conf.task_default_queue = "capagg-default"
