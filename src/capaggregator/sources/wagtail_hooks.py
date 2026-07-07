"""Wagtail admin integration (each app owns its admin surface via wagtail_hooks.py).

Planned admin surface (docs/design.md §8):
- Authority registry with an "issue MQTT credentials" action showing the
  one-time password + copy-paste cap-composer broker instructions
- Quarantine inbox with validation reports + notify-authority action
- Ingestion monitor (RawMessage states, latency)
- Geocode registry with bulk import
"""

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from .models import SourceAuthority


class SourceAuthorityViewSet(SnippetViewSet):
    model = SourceAuthority
    icon = "globe"
    menu_label = "Authorities"
    list_display = ["name", "country", "slug", "feed_url", "feed_type_detected", "mqtt_topic", "active"]
    list_filter = ["country", "active"]
    search_fields = ["name", "slug", "sender_values"]


class SourcesGroup(SnippetViewSetGroup):
    menu_label = "CAP Sources"
    menu_icon = "globe"
    items = [SourceAuthorityViewSet]


register_snippet(SourcesGroup)
