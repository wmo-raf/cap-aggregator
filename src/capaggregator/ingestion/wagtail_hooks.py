from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

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
    list_filter = ["status"]
    inspect_view_enabled = True


class IngestionGroup(SnippetViewSetGroup):
    menu_label = "Ingestion"
    menu_icon = "download"
    items = [RawMessageViewSet, QuarantineViewSet]


register_snippet(IngestionGroup)
