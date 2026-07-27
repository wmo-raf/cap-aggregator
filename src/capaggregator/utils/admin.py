"""Shared Wagtail admin helpers."""

from wagtail.permission_policies import ModelPermissionPolicy
from wagtail.snippets.bulk_actions.snippet_bulk_action import SnippetBulkAction
from wagtail.snippets.models import get_snippet_models


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


def is_read_only_register(model):
    """True when the model's snippet register is declared read-only."""
    viewset = getattr(model, "snippet_viewset", None)
    return isinstance(getattr(viewset, "permission_policy", None), ReadOnlyPermissionPolicy)


class _WritableSnippetModels:
    """The catch-all model list a generic snippet bulk action claims, minus the
    read-only registers. Kept lazy — like the classproperty it replaces — because
    the snippet registry is only complete once every `wagtail_hooks` has been
    imported."""

    def __get__(self, instance, cls=None):
        return [model for model in get_snippet_models() if not is_read_only_register(model)]


def restrict_generic_bulk_actions_to_writable_registers():
    """Wagtail registers Delete for *every* snippet model and gates it on the
    Django `delete_<model>` permission, so it ignores a viewset's permission
    policy and a superuser gets it on our immutable registers. Worse, its "select
    all in the listing" defaults to the whole table rather than the filtered rows.

    There is no per-viewset opt-out: the footer buttons come from the global
    `bulk_action_registry` via the `bulk_action_choices` templatetag, which does
    no permission filtering. Narrowing the catch-all model list is the one edit
    that both stops the button rendering and leaves nothing for a hand-made POST
    to reach (the dispatcher 404s on an unregistered action).

    Scoped to the catch-all: an action that names its models explicitly — our
    Dismiss — has opted a register in deliberately and is left alone."""
    SnippetBulkAction.models = _WritableSnippetModels()


# Installed on import, which any read-only register triggers by importing the
# policy above. The descriptor is inert until the bulk-action registry does its
# one-time scan on the first admin listing, so import order does not matter.
restrict_generic_bulk_actions_to_writable_registers()
