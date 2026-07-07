from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.permission_policies import ModelPermissionPolicy
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from .admin_views import backfill_upload, quarantine_dismiss, quarantine_revalidate
from .models import QuarantinedMessage, RawMessage


class ReadOnlyPermissionPolicy(ModelPermissionPolicy):
    """Deny add/change/delete for everyone (even superusers) — the admin surface
    is read-only. Raw messages are immutable; only list/inspect are allowed."""

    def user_has_permission(self, user, action):
        if action in {"add", "change", "delete"}:
            return False
        return super().user_has_permission(user, action)

    def user_has_permission_for_instance(self, user, action, instance):
        if action in {"add", "change", "delete"}:
            return False
        return super().user_has_permission_for_instance(user, action, instance)


class RawMessageViewSet(SnippetViewSet):
    model = RawMessage
    icon = "download"
    menu_label = "Raw Messages"
    list_display = ["sha256", "authority", "transport", "state", "received_at", "ingest_latency"]
    list_filter = ["state", "transport", "authority"]
    inspect_view_enabled = True
    permission_policy = ReadOnlyPermissionPolicy(RawMessage)


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
