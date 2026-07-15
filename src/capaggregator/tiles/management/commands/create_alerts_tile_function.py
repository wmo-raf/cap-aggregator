"""Management command: create_alerts_tile_function

Creates/replaces the PostgreSQL function source used by Martin to serve
resolved alerts as vector tiles. Martin calls it via:

    GET /tiles/alerts/{z}/{x}/{y}
        ?t=2026-07-06T12:00:00Z            (point in time; default now())
        &severity=Severe,Extreme           (CSV filters, all optional)
        &urgency=Immediate
        &certainty=Observed,Likely
        &category=Met
        &msg_type=Alert,Update
        &status=Actual
        &country=ke
        &event=flood

Two MVT layers per tile:
  - alerts          polygon fills (simplification by zoom: geom_z5 / geom_z8 / geom)
  - alert_centroids centroid points for low-zoom symbols

Animation = the client stepping `t` and re-requesting tiles; round `t` to
5-minute buckets client-side so tile URLs hit the nginx proxy cache.

Usage:
    capagg create_alerts_tile_function
    capagg create_alerts_tile_function --drop
"""

from django.core.management.base import BaseCommand
from django.db import connection

_CREATE_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION capagg_alerts_tile(
    z           integer,
    x           integer,
    y           integer,
    query_params json DEFAULT '{}'
)
RETURNS bytea
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
AS $func$
DECLARE
    fills       bytea;
    points      bytea;
    t           timestamptz := COALESCE(NULLIF(query_params->>'t', '')::timestamptz, now());
    f_severity  text[] := string_to_array(NULLIF(query_params->>'severity', ''), ',');
    f_urgency   text[] := string_to_array(NULLIF(query_params->>'urgency', ''), ',');
    f_certainty text[] := string_to_array(NULLIF(query_params->>'certainty', ''), ',');
    f_category  text[] := string_to_array(NULLIF(query_params->>'category', ''), ',');
    f_msg_type  text[] := string_to_array(NULLIF(query_params->>'msg_type', ''), ',');
    f_status    text[] := string_to_array(NULLIF(query_params->>'status', ''), ',');
    f_country   text[] := string_to_array(lower(NULLIF(query_params->>'country', '')), ',');
    f_event     text   := NULLIF(query_params->>'event', '');
    tile_env    geometry := ST_TileEnvelope(z, x, y);
    tile_bbox   geometry := ST_Transform(tile_env, 4326);
BEGIN
    WITH candidates AS (
        SELECT
            r.id,
            r.chain_id AS chain,
            r.event,
            r.headline,
            r.msg_type,
            r.status,
            r.severity,
            r.urgency,
            r.certainty,
            r.categories,
            r.countries,
            r.is_cancelled,
            r.effective,
            r.expires,
            r.onset,
            a.slug          AS authority,
            -- choose simplification level by zoom
            CASE WHEN z <= 5 THEN COALESCE(r.geom_z5, r.geom)
                 WHEN z <= 8 THEN COALESCE(r.geom_z8, r.geom)
                 ELSE r.geom
            END             AS geom,
            r.centroid
        FROM capagg_alerts_resolvedalert r
        JOIN capagg_sources_sourceauthority a ON a.id = r.authority_id
        WHERE r.geom IS NOT NULL
          AND NOT r.is_cancelled
          AND COALESCE(r.effective, '-infinity'::timestamptz) <= t
          AND COALESCE(r.expires,   'infinity'::timestamptz)  >  t
          AND (f_severity  IS NULL OR r.severity  = ANY(f_severity))
          AND (f_urgency   IS NULL OR r.urgency   = ANY(f_urgency))
          AND (f_certainty IS NULL OR r.certainty = ANY(f_certainty))
          AND (f_msg_type  IS NULL OR r.msg_type  = ANY(f_msg_type))
          AND (f_status    IS NULL OR r.status    = ANY(f_status))
          AND (f_category  IS NULL OR r.categories::text[] && f_category)
          AND (f_country   IS NULL OR r.countries::text[]  && f_country)
          AND (f_event     IS NULL OR r.event ILIKE '%%' || f_event || '%%')
          AND r.geom && tile_bbox
    ),
    fill_layer AS (
        SELECT ST_AsMVT(q.*, 'alerts', 4096, 'mvt_geom') AS mvt
        FROM (
            SELECT
                id, chain, event, headline, msg_type, status, severity, urgency,
                certainty, authority,
                array_to_string(countries, ',')  AS countries,
                array_to_string(categories, ',') AS categories,
                effective, expires, onset,
                ST_AsMVTGeom(ST_Transform(geom, 3857), tile_env, 4096, 64, true) AS mvt_geom
            FROM candidates
        ) q
        WHERE q.mvt_geom IS NOT NULL
    ),
    point_layer AS (
        SELECT ST_AsMVT(q.*, 'alert_centroids', 4096, 'mvt_geom') AS mvt
        FROM (
            SELECT
                id, chain, event, severity, urgency, certainty,
                ST_AsMVTGeom(ST_Transform(centroid, 3857), tile_env, 4096, 64, true) AS mvt_geom
            FROM candidates
            WHERE centroid IS NOT NULL
        ) q
        WHERE q.mvt_geom IS NOT NULL
    )
    SELECT COALESCE((SELECT mvt FROM fill_layer), ''::bytea)
        || COALESCE((SELECT mvt FROM point_layer), ''::bytea)
    INTO fills;

    RETURN fills;
END
$func$;

COMMENT ON FUNCTION capagg_alerts_tile IS
  'Martin function source: resolved CAP alerts as MVT, filtered by time + CAP fields';
"""

_DROP_FUNCTION_SQL = "DROP FUNCTION IF EXISTS capagg_alerts_tile(integer, integer, integer, json);"


class Command(BaseCommand):
    help = "Create or replace the capagg_alerts_tile() Martin function source"

    def add_arguments(self, parser):
        parser.add_argument("--drop", action="store_true", help="Drop the function only")

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute(_DROP_FUNCTION_SQL)
            if options["drop"]:
                self.stdout.write(self.style.SUCCESS("Dropped capagg_alerts_tile"))
                return
            cursor.execute(_CREATE_FUNCTION_SQL)
        self.stdout.write(self.style.SUCCESS("Created capagg_alerts_tile — served by Martin at /tiles/alerts/{z}/{x}/{y}"))
