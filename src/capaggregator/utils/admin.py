"""Shared Wagtail admin helpers."""

from wagtail.permission_policies import ModelPermissionPolicy


class RelatedListingMixin:
    """Pull the related objects a list's columns read, so no column fires a
    query per row. Set `list_select_related` / `list_prefetch_related` on the
    viewset; `SnippetViewSet.get_queryset` returns None to mean 'default
    manager', which is the case the guard below covers."""

    list_select_related: list[str] = []
    list_prefetch_related: list[str] = []

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if qs is None:
            qs = self.model._default_manager.all()
        if self.list_select_related:
            qs = qs.select_related(*self.list_select_related)
        if self.list_prefetch_related:
            qs = qs.prefetch_related(*self.list_prefetch_related)
        return qs


class ReadOnlyPermissionPolicy(ModelPermissionPolicy):
    """Deny add/change/delete for everyone (even superusers) — the admin surface
    is read-only. Raw messages, stored alerts and defect rows are immutable
    records; only list/inspect are allowed."""

    def user_has_permission(self, user, action):
        if action in {"add", "change", "delete"}:
            return False
        return super().user_has_permission(user, action)

    def user_has_permission_for_instance(self, user, action, instance):
        if action in {"add", "change", "delete"}:
            return False
        return super().user_has_permission_for_instance(user, action, instance)
