"""PROTOTYPE — throwaway harness to eyeball Martin vector-tile rendering.

Wired only under settings.DEBUG (see config/urls.py). Renders a MapLibre map that
pulls the `alerts` Martin source through the nginx same-origin proxy (/tiles/…),
with a time slider because the tile function filters by `t` and "now" is usually
empty. DELETE this file, its template, and the urls.py entry once rendering is
verified. Question it answers: "do the Martin tiles actually render?"
"""

from django.db.models import Max, Min
from django.shortcuts import render


def proto_tiles(request):
    from capaggregator.alerts.models import ResolvedAlert

    agg = ResolvedAlert.objects.filter(is_cancelled=False, geom__isnull=False).aggregate(
        tmin=Min("effective"), tmax=Max("expires"), tdefault=Max("effective")
    )
    return render(
        request,
        "proto_tiles.html",
        {
            "t_min": agg["tmin"].isoformat() if agg["tmin"] else "",
            "t_max": agg["tmax"].isoformat() if agg["tmax"] else "",
            "t_default": agg["tdefault"].isoformat() if agg["tdefault"] else "",
        },
    )
