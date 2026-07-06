"""Task-ferry job type for bulk geocode imports.

    from task_ferry.handler import JobHandler
    JobHandler.create_and_start(user, "geocode_import",
                                scheme_id=..., file_path=..., file_format="geojson")
"""

import csv
import json
import logging
from pathlib import Path

from task_ferry.registry import JobType

from .models import GeocodeImportJob

logger = logging.getLogger(__name__)


class GeocodeImportJobType(JobType):
    type = "geocode_import"
    model_class = GeocodeImportJob
    max_count = 2

    def prepare_values(self, values: dict, user) -> dict:
        from .models import GeocodeScheme

        scheme_id = values.get("scheme_id") or values.get("scheme")
        file_path = values.get("file_path")
        if not scheme_id:
            raise ValueError("'scheme_id' is required for a geocode import job.")
        if not file_path or not Path(file_path).is_file():
            raise ValueError(f"'file_path' missing or not a file: {file_path}")

        file_format = values.get("file_format", "geojson")
        if file_format not in ("geojson", "csv"):
            raise ValueError("file_format must be 'geojson' or 'csv'")

        return {
            "scheme": GeocodeScheme.objects.get(pk=scheme_id),
            "file_path": str(file_path),
            "file_format": file_format,
            "valid_from": values.get("valid_from"),
        }

    def run(self, job: GeocodeImportJob, progress) -> None:
        progress.increment(5, state="Reading input file…")
        records = list(_read_records(job.file_path, job.file_format))

        if not records:
            progress.increment(95, state="No records found in file")
            return

        work = progress.create_child(represents=95, total=len(records))
        for value, name, geom in records:
            outcome = _upsert_value(job, value, name, geom)
            if outcome == "created":
                job.values_created += 1
            elif outcome == "updated":
                job.values_updated += 1
            else:
                job.values_skipped += 1
            work.increment(state=f"Imported {value}")

        job.save(update_fields=["values_created", "values_updated", "values_skipped"])


def _read_records(file_path: str, file_format: str):
    """Yield (value, name, MultiPolygon) tuples from GeoJSON or CSV+WKT."""
    from django.contrib.gis.geos import GEOSGeometry, MultiPolygon

    def as_multipolygon(geom):
        if geom.geom_type == "Polygon":
            geom = MultiPolygon(geom, srid=4326)
        if geom.srid is None:
            geom.srid = 4326
        return geom

    if file_format == "geojson":
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        for feature in data.get("features", []):
            props = feature.get("properties") or {}
            value = props.get("value") or props.get("code") or props.get("id")
            if not value or not feature.get("geometry"):
                logger.info("Skipping feature without value/geometry: %.80s", props)
                continue
            geom = as_multipolygon(GEOSGeometry(json.dumps(feature["geometry"])))
            yield str(value), str(props.get("name", "")), geom
    else:  # csv with columns: value, name, wkt
        with open(file_path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                value, wkt = row.get("value"), row.get("wkt")
                if not value or not wkt:
                    continue
                yield str(value), str(row.get("name", "")), as_multipolygon(GEOSGeometry(wkt))


def _upsert_value(job, value: str, name: str, geom) -> str:
    """Versioned upsert: if a current row exists with a different geometry,
    close its validity window and create a new version (admin boundaries change)."""
    from django.utils import timezone

    from .models import GeocodeValue

    valid_from = job.valid_from or timezone.now()
    current = GeocodeValue.objects.filter(scheme=job.scheme, value=value, valid_to__isnull=True).first()

    if current is None:
        GeocodeValue.objects.create(scheme=job.scheme, value=value, name=name,
                                    geom=geom, valid_from=job.valid_from)
        return "created"

    if current.geom.equals(geom):
        if name and current.name != name:
            current.name = name
            current.save(update_fields=["name"])
            return "updated"
        return "skipped"

    # Geometry changed → version it
    current.valid_to = valid_from
    current.save(update_fields=["valid_to"])
    GeocodeValue.objects.create(scheme=job.scheme, value=value, name=name,
                                geom=geom, valid_from=valid_from)
    return "updated"
