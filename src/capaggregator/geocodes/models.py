"""Versioned geocode registry — maps CAP <geocode> values (EMMA_ID, ISO 3166-2,
FIPS, national schemes) to geometries. Admin boundaries change over time, so
values carry validity windows; resolution picks the version valid at the
alert's <sent> time."""

from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils.translation import gettext_lazy as _


class GeocodeScheme(models.Model):
    name = models.CharField(max_length=100, unique=True,
                            help_text=_("CAP geocode valueName, e.g. 'EMMA_ID', 'ISO 3166-2'"))
    description = models.TextField(blank=True)
    authority = models.ForeignKey("capagg_sources.SourceAuthority", null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name="geocode_schemes",
                                  help_text=_("Set for national schemes; empty for global ones"))

    def __str__(self):
        return self.name


class GeocodeValue(gis_models.Model):
    scheme = models.ForeignKey(GeocodeScheme, on_delete=models.CASCADE, related_name="values")
    value = models.CharField(max_length=100)
    name = models.CharField(max_length=255, blank=True)
    geom = gis_models.MultiPolygonField(srid=4326)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["scheme", "value"])]

    def __str__(self):
        return f"{self.scheme.name}:{self.value}"


# ---------------------------------------------------------------------------
# Task-ferry Job models
# ---------------------------------------------------------------------------

from task_ferry.models import Job  # noqa: E402


class GeocodeImportJob(Job):
    """Bulk import of geocode values into a scheme from GeoJSON (features with
    'value'/'name' properties) or CSV with a WKT geometry column."""

    FORMATS = (("geojson", "GeoJSON"), ("csv", "CSV (WKT column)"))

    scheme = models.ForeignKey(GeocodeScheme, on_delete=models.CASCADE, related_name="import_jobs")
    file_path = models.CharField(max_length=500)
    file_format = models.CharField(max_length=10, choices=FORMATS, default="geojson")
    valid_from = models.DateTimeField(null=True, blank=True,
                                      help_text=_("Validity window start for imported values"))
    values_created = models.IntegerField(default=0)
    values_updated = models.IntegerField(default=0)
    values_skipped = models.IntegerField(default=0)
