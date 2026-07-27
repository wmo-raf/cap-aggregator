"""The Alerts admin group: the defect register and an inspect-only alert view.

Both surfaces are read-only. A stored alert is an immutable record of what an
authority published, and a defect row is the evidence behind a conformance
conversation — neither is something an operator edits.
"""

from django.urls import reverse
from wagtail.admin.ui.tables import Column, TitleColumn
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from capaggregator.utils.admin import ReadOnlyPermissionPolicy

from .models import Alert, AlertDefect

ALERT_INSPECT_URL_NAME = "wagtailsnippets_capagg_alerts_alert:inspect"


class AlertDefectViewSet(SnippetViewSet):
    model = AlertDefect
    icon = "warning"
    menu_label = "Defects"
    list_display = [
        "created",
        TitleColumn("alert", label="Alert",
                    get_url=lambda defect: reverse(ALERT_INSPECT_URL_NAME, args=[defect.alert_id])),
        Column("authority", label="Authority", accessor="alert.authority"),
        "category",
        Column("check_name", label="Check"),
        "severity",
        "message",
    ]
    list_filter = ["category", "severity", "alert__authority"]
    inspect_view_enabled = True
    inspect_view_fields = ["alert", "category", "check_name", "severity", "message", "created"]
    permission_policy = ReadOnlyPermissionPolicy(AlertDefect)

    def get_queryset(self, request):
        # The list shows the alert and its authority on every row.
        qs = super().get_queryset(request)
        if qs is None:
            qs = self.model._default_manager.all()
        return qs.select_related("alert", "alert__authority")


class AlertViewSet(SnippetViewSet):
    model = Alert
    icon = "warning"
    menu_label = "Alerts"
    list_display = [
        "sent",
        "identifier",
        "authority",
        "msg_type",
        "status",
        Column("defect_count", label="Defects"),
    ]
    list_filter = ["msg_type", "status", "authority"]
    inspect_view_enabled = True
    inspect_view_fields = [
        "identifier", "sender", "sent", "msg_type", "status", "scope", "authority",
        "references", "note", "signature_valid", "defect_count", "created",
    ]
    inspect_template_name = "capagg_alerts/alert_inspect.html"
    permission_policy = ReadOnlyPermissionPolicy(Alert)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if qs is None:
            qs = self.model._default_manager.all()
        return qs.select_related("authority")


class AlertsGroup(SnippetViewSetGroup):
    menu_label = "Alerts"
    menu_icon = "warning"
    items = [AlertViewSet, AlertDefectViewSet]


register_snippet(AlertsGroup)
