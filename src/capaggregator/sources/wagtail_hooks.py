"""Wagtail admin integration (each app owns its admin surface via wagtail_hooks.py).

Planned admin surface (docs/design.md §8):
- Authority registry with an "issue MQTT credentials" action showing the
  one-time password + copy-paste cap-composer broker instructions
- Quarantine inbox with validation reports + notify-authority action
- Ingestion monitor (RawMessage states, latency)
- Geocode registry with bulk import
"""

from django.urls import path
from wagtail import hooks
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from .admin_views import issue_mqtt_credentials
from .models import SourceAuthority


class SourceAuthorityViewSet(SnippetViewSet):
    model = SourceAuthority
    icon = "globe"
    menu_label = "Authorities"
    list_display = ["name", "country", "slug", "feed_url", "feed_type_detected", "has_mqtt_credentials", "active"]
    list_filter = ["country", "active"]
    search_fields = ["name", "slug", "sender_values"]
    inspect_view_enabled = True
    inspect_view_fields = ["name", "country", "sender_values", "feed_url", "mqtt_username", "mqtt_topic", "active"]
    inspect_template_name = "capagg_sources/authority_inspect.html"


class SourcesGroup(SnippetViewSetGroup):
    menu_label = "CAP Sources"
    menu_icon = "globe"
    items = [SourceAuthorityViewSet]


register_snippet(SourcesGroup)


@hooks.register("register_admin_urls")
def register_issue_mqtt_url():
    return [
        path("capagg-sources/<int:pk>/issue-mqtt/", issue_mqtt_credentials, name="capagg_sources_issue_mqtt"),
    ]
