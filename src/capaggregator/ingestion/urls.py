from django.urls import path

from . import views

urlpatterns = [
    # cap-composer webhook fallback: configure https://<aggregator>/api/ingest/webhook/<token>/
    path("webhook/<str:token>/", views.webhook_ingest, name="webhook_ingest"),
]
