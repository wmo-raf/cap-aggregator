from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from . import views

urlpatterns = [
    # Async job status/progress (django-task-ferry)
    path("jobs/", include("task_ferry.api.urls", namespace="task_ferry")),
    path("schema/", SpectacularAPIView.as_view(), name="api_schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api_schema"), name="api_docs"),
    # Search over resolved state (country, severity, urgency, certainty, category,
    # event, msg_type, status, language, bbox, time interval, full-text q)
    path("search/", views.AlertSearchView.as_view(), name="alert_search"),
    # Active authorities + current alert activity (explorer Authorities view)
    path("authorities/", views.AuthorityListView.as_view(), name="authority_list"),
    # Alert counts per time bucket — powers the time-slider density histogram
    path("histogram/", views.histogram, name="alert_histogram"),
    # SSE stream of alert ids for live mode (Redis pub/sub 'capagg:alerts')
    path("events/stream/", views.event_stream, name="event_stream"),
]
