import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "capaggregator.config.settings.dev")

app = Celery("capaggregator")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Queue conventions:
#   capagg-ingestion — heavy pipeline work (validate/parse/resolve)
#   capagg-default   — everything else (notifications, re-publication, metrics)
app.conf.task_routes = {
    "capaggregator.ingestion.tasks.*": {"queue": "capagg-ingestion"},
    "capaggregator.alerts.tasks.*": {"queue": "capagg-ingestion"},
    "*": {"queue": "capagg-default"},
}
app.conf.task_default_queue = "capagg-default"
