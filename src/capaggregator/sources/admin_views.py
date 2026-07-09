"""Wagtail admin view: issue / regenerate an authority's MQTT credentials.

GET renders a confirmation page; POST issues the credentials and renders a
one-time result page (the plaintext password is held in memory for that response
only — it is never stored or shown again). Issuing persists the model, whose
post-save signal syncs the broker auth files.
"""

from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from wagtail.admin import messages
from wagtail.admin.auth import require_admin_access

from .models import SourceAuthority
from .registry import apply_registry_selection, derive_registry_view, fetch_wmo_registry, parse_wmo_registry


@require_admin_access
def issue_mqtt_credentials(request, pk):
    authority = get_object_or_404(SourceAuthority, pk=pk)

    if request.method == "POST":
        password = authority.issue_mqtt_credentials()
        authority.refresh_from_db()
        return render(request, "capagg_sources/issue_mqtt_result.html", {
            "authority": authority,
            "password": password,
            "mqtt_host": settings.MQTT_HOST,
            "mqtt_port": settings.MQTT_PORT,
        })

    return render(request, "capagg_sources/issue_mqtt_confirm.html", {"authority": authority})


@require_admin_access
def wmo_registry_picker(request):
    """Picker over the WMO Register of Alerting Authorities. GET (issue #28)
    fetches (cached) + parses the live register and shows each entry with an
    import status and a selection checkbox on selectable rows. POST (issue #29)
    bulk-creates a SourceAuthority for each selected NEW entry, then redirects
    to the Authorities list with a summary message."""
    if request.method == "POST":
        content, error = fetch_wmo_registry()
        if error:
            messages.error(request, error)
            return redirect(reverse("capagg_sources_wmo_registry"))
        summary = apply_registry_selection(parse_wmo_registry(content), request.POST.getlist("guid"))
        messages.success(request, _("Created %(created)d authorities (%(skipped)d skipped).") % {
            "created": summary.created, "skipped": summary.skipped,
        })
        return redirect(reverse("wagtailsnippets_capagg_sources_sourceauthority:list"))

    refresh = request.GET.get("refresh") == "1"
    content, error = fetch_wmo_registry(refresh=refresh)

    rows = []
    if content is not None:
        rows = derive_registry_view(parse_wmo_registry(content))

    return render(request, "capagg_sources/wmo_registry_picker.html", {"rows": rows, "error": error})
