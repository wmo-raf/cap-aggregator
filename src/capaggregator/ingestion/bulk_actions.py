"""Bulk actions on the withheld register.

Dismissal is the register's only write, and with the edit view gone it is also
its only bulk path. One authority already holds dozens of withheld re-issues
from a single upstream bug, so "select all in the listing" has to mean *all the
rows the current filters describe* — never the whole table.
"""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext
from wagtail.snippets.bulk_actions.snippet_bulk_action import SnippetBulkAction

from .filters import WithheldFilterSet
from .models import QuarantinedMessage


class DismissBulkAction(SnippetBulkAction):
    display_name = _("Dismiss")
    action_type = "dismiss"
    aria_label = _("Dismiss selected withheld messages")
    template_name = "capagg_ingestion/bulk_actions/confirm_bulk_dismiss.html"
    models = [QuarantinedMessage]

    @classmethod
    def get_queryset(cls, model, object_ids):
        """Wagtail's default 404s on an empty selection. Here an empty selection
        is an ordinary answer — filters that match nothing — so the confirmation
        page says there is nothing to dismiss instead of showing an error."""
        return model.objects.filter(pk__in=object_ids)

    def get_all_objects_in_listing_query(self, parent_id):
        """The rows behind "select all in the listing" — which is the filtered
        listing, not the table. Wagtail's JS forwards the list's querystring, so
        running it back through the list's own filterset is what keeps the two
        views of "all" in agreement."""
        filterset = WithheldFilterSet(
            self.request.GET, queryset=QuarantinedMessage.objects.all(), request=self.request
        )
        if not filterset.is_valid():
            # Filters we cannot read describe no listing, so they select nothing
            # — the one answer that cannot dismiss rows the operator never saw.
            return QuarantinedMessage.objects.none().values_list("pk", flat=True)
        return filterset.qs.values_list("pk", flat=True)

    def check_perm(self, obj):
        """Dismissal is not an edit, so it takes the same permission as reading
        the register. Spelled out because `BulkAction.check_perm` defaults to
        allowing everyone, and the register's read-only policy denies `change`
        — leaving it to the default would mean neither rule applied."""
        return self.model.snippet_viewset.permission_policy.user_has_permission(self.request.user, "view")

    def object_context(self, obj):
        # No edit URL to offer: the register is read-only.
        return {"item": obj}

    @classmethod
    def execute_action(cls, objects, **kwargs):
        QuarantinedMessage.objects.filter(pk__in=[obj.pk for obj in objects]).dismiss()
        return len(objects), 0

    def get_success_message(self, num_parent_objects, num_child_objects):
        if not num_parent_objects:
            return _("No withheld messages matched — nothing was dismissed.")
        return ngettext(
            "%(count)d withheld message dismissed.",
            "%(count)d withheld messages dismissed.",
            num_parent_objects,
        ) % {"count": num_parent_objects}
