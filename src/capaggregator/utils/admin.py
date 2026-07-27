"""Shared Wagtail admin helpers."""

from wagtail.permission_policies import ModelPermissionPolicy


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
