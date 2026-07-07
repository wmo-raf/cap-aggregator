"""Wagtail admin view: issue / regenerate an authority's MQTT credentials.

GET renders a confirmation page; POST issues the credentials and renders a
one-time result page (the plaintext password is held in memory for that response
only — it is never stored or shown again). Issuing persists the model, whose
post-save signal syncs the broker auth files.
"""

from django.conf import settings
from django.shortcuts import get_object_or_404, render
from wagtail.admin.auth import require_admin_access

from .models import SourceAuthority


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
