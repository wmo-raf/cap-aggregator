from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.ui.components import Component
from wagtail.admin.ui.tables import Column
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from capaggregator.utils.admin import ReadOnlyPermissionPolicy, RelatedListingMixin

from .admin_views import (
    WithheldInspectView,
    authority_monitor,
    backfill_upload,
    health_dashboard_api,
    quarantine_dismiss,
    quarantine_revalidate,
)
from .models import QuarantinedMessage, RawMessage, SourceEvent


class RawMessageViewSet(RelatedListingMixin, SnippetViewSet):
    model = RawMessage
    icon = "download"
    menu_label = "Raw Messages"
    list_display = [
        "received_at",
        "authority",
        Column("alert_title", label="Title"),
        "transport",
        "state",
        "sent_at",
        Column("ingest_latency_display", label="Latency"),
    ]
    list_filter = ["state", "transport", "authority"]
    inspect_view_enabled = True
    # The `alert_title` column walks into the alert's info blocks.
    list_prefetch_related = ["alerts__infos"]
    permission_policy = ReadOnlyPermissionPolicy(RawMessage)


class QuarantineViewSet(SnippetViewSet):
    model = QuarantinedMessage
    icon = "warning"
    menu_label = "Quarantine"
    list_display = ["raw_message", Column("category_label", label="Category"), "status", "created"]
    list_filter = ["primary_category", "status", "raw_message__authority"]
    inspect_view_enabled = True
    # The template renders provenance, findings and the raw CAP itself, so the
    # generic field table would only repeat it in a less legible order.
    inspect_view_class = WithheldInspectView
    inspect_template_name = "capagg_ingestion/quarantine_inspect.html"
    list_select_related = ["raw_message", "raw_message__authority"]


class SourceEventViewSet(SnippetViewSet):
    model = SourceEvent
    icon = "list-ul"
    menu_label = "Transport Events"
    list_display = ["authority", "transport", "ok", "occurred_at", "error"]
    list_filter = ["transport", "ok", "authority"]
    inspect_view_enabled = True
    permission_policy = ReadOnlyPermissionPolicy(SourceEvent)


class IngestionGroup(SnippetViewSetGroup):
    menu_label = "Ingestion"
    menu_icon = "download"
    items = [RawMessageViewSet, QuarantineViewSet, SourceEventViewSet]


register_snippet(IngestionGroup)


@hooks.register("register_admin_urls")
def register_backfill_admin_url():
    return [
        path("capagg-backfill/", backfill_upload, name="capagg_ingestion_backfill_upload"),
        path("capagg-quarantine/revalidate/", quarantine_revalidate, name="capagg_ingestion_quarantine_revalidate"),
        path("capagg-quarantine/<int:pk>/dismiss/", quarantine_dismiss, name="capagg_ingestion_quarantine_dismiss"),
        path("capagg-health/dashboard.json", health_dashboard_api, name="capagg_ingestion_health_api"),
        path("capagg-sources/<int:pk>/monitor/", authority_monitor, name="capagg_ingestion_authority_monitor"),
    ]


@hooks.register("register_admin_menu_item")
def register_backfill_menu_item():
    return MenuItem("CAP backfill", reverse("capagg_ingestion_backfill_upload"), icon_name="upload")


class HealthPanel(Component):
    order = 200
    template_name = "capagg_ingestion/health_panel.html"

    def get_context_data(self, parent_context):
        context = super().get_context_data(parent_context)
        context["api_url"] = reverse("capagg_ingestion_health_api")
        return context


@hooks.register("construct_homepage_panels")
def add_health_panel(request, panels):
    panels.append(HealthPanel())
