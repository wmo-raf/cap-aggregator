from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from .views import health

urlpatterns = [
    path("health/", health, name="health"),
    path("django-admin/", admin.site.urls),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("api/", include("capaggregator.api.urls")),
    path("api/ingest/", include("capaggregator.ingestion.urls")),
    # Public alert detail pages (chain-canonical)
    path("alerts/", include("capaggregator.alerts.urls")),
    # Explorer SPA shell — everything under /explorer/ is routed client-side
    re_path(r"^explorer/", include("capaggregator.home.urls")),
    path("", include(wagtail_urls)),
]

if settings.DEBUG:
    from capaggregator.tiles.proto_tiles import proto_tiles  # PROTOTYPE — delete with the file

    urlpatterns = (
        static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
        + [path("proto/tiles/", proto_tiles, name="proto_tiles")]  # PROTOTYPE — throwaway
        + urlpatterns
    )
