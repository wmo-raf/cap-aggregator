from django.conf import settings


def version(request):
    """Expose the app version (capaggregator/version.py) to all templates —
    rendered in the public footer."""
    return {"CAPAGG_VERSION": settings.VERSION}
