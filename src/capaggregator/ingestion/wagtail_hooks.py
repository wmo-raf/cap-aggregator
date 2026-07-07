from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from .admin_views import backfill_upload, quarantine_dismiss, quarantine_revalidate
from .models import QuarantinedMessage, RawMessage


class RawMessageViewSet(SnippetViewSet):
    model = RawMessage
    icon = "download"
    menu_label = "Raw Messages"
    list_display = ["sha256", "authority", "transport", "state", "received_at"]
    list_filter = ["state", "transport"]
    inspect_view_enabled = True


class QuarantineViewSet(SnippetViewSet):
    model = QuarantinedMessage
    icon = "warning"
    menu_label = "Quarantine"
    list_display = ["raw_message", "status", "created"]
    list_filter = ["status", "raw_message__authority"]
    inspect_view_enabled = True
    inspect_view_fields = ["raw_message", "status", "report_summary", "created", "modified"]
    inspect_template_name = "capagg_ingestion/quarantine_inspect.html"


class IngestionGroup(SnippetViewSetGroup):
    menu_label = "Ingestion"
    menu_icon = "download"
    items = [RawMessageViewSet, QuarantineViewSet]


register_snippet(IngestionGroup)


@hooks.register("register_admin_urls")
def register_backfill_admin_url():
    return [
        path("capagg-backfill/", backfill_upload, name="capagg_ingestion_backfill_upload"),
        path("capagg-quarantine/revalidate/", quarantine_revalidate, name="capagg_ingestion_quarantine_revalidate"),
        path("capagg-quarantine/<int:pk>/dismiss/", quarantine_dismiss, name="capagg_ingestion_quarantine_dismiss"),
    ]


@hooks.register("register_admin_menu_item")
def register_backfill_menu_item():
    return MenuItem("CAP backfill", reverse("capagg_ingestion_backfill_upload"), icon_name="upload")
