# Architectural Patterns

Recurring conventions in this codebase. Each is used in multiple places — follow
them when adding code rather than inventing a new style.

## App layout (Django apps as bounded contexts)

Each domain lives in its own app under `src/capaggregator/`, with a stable
internal shape. Apps use short DB labels via `AppConfig.label` (`capagg_sources`,
`capagg_ingestion`, `capagg_alerts`, …) — see `sources/apps.py:7`. Cross-app FKs
reference by that label string, never by import: e.g.
`"capagg_sources.SourceAuthority"` in `alerts/models.py:25`.

Per-app file conventions:
- `models.py` — models + Wagtail `panels`
- `tasks.py` — Celery tasks
- `wagtail_hooks.py` — admin surface (see below)
- `apps.py` `ready()` — signal wiring / registry registration
- `job_types.py` — task-ferry job types (where async progress is needed)

## Celery task conventions

Tasks follow a fixed decorator + import discipline (documented at
`ingestion/tasks.py:1`):

- `@shared_task(bind=True, acks_late=True)`; the main pipeline entry point adds
  `max_retries=0` and relies on a periodic **sweep** task for recovery
  (`ingestion/tasks.py:142` `sweep_unprocessed` re-runs rows stuck in `received`).
- **Late imports inside the task body**, not at module top — keeps task modules
  importable by the Django app registry before models are ready. This is
  pervasive: every task and `run_pipeline` imports models locally.
- Queue routing is centralized in `config/celery.py:14`: ingestion/alerts tasks →
  `capagg-ingestion`, everything else → `capagg-default`. Don't set queues on
  individual tasks.
- Reliability settings (`acks_late`, `reject_on_worker_lost`, `prefetch=1`) are
  global in `config/settings/base.py:198`.

## Reusable pipeline core, thin task wrapper

Business logic lives in a plain function that operates on already-persisted rows;
the Celery task is a thin wrapper. `run_pipeline(raw, ...)` in
`ingestion/tasks.py:29` does validate → store → receipt → lineage and is reused by
three callers: the `ingest_raw_message` task, the backfill job, and the quarantine
re-validation job (`ingestion/job_types.py:110`). When adding processing logic,
extend the plain function so all entry points share it.

## Registry + decorator extension points

Two pluggable registries let features be added without editing the caller:

- **Validator registry** (`ingestion/validators.py:49`): semantic rules register
  via `@validator_registry.register("check-name")` and receive
  `(tree, raw, report)`. A rule that raises is caught and downgraded to a warning
  so one bad rule can't kill the pipeline (`validators.py:66`).
- **Task-ferry job registry**: job types subclass `JobType`, are registered in the
  app's `ready()` (`ingestion/apps.py:9`), and expose progress via
  `progress.increment(...)` / `progress.create_child(...)`.

## Validation report as structured data

Validation never raises to signal failure — it accumulates into a
`ValidationReport` dataclass (`ingestion/validators.py:27`) with `errors` and
`warnings`. **Errors → quarantine; warnings → stored with the alert.** The report
serializes to JSON (`as_dict()`) into `QuarantinedMessage.report` and
`Alert.validation_warnings`. Nothing is ever silently dropped.

## Immutable-store-first, dedup, receipts

Ingestion treats CAP messages as immutable and content as first-wins across
transports (`ingestion/tasks.py:1` docstring). The pattern:

- Two-layer dedup: sha256 of exact bytes (`ingest_raw_message`), then the CAP
  identity triple `(sender, identifier, sent)` after a cheap parse
  (`parse_identity` in `alerts/parser.py:22`).
- A DB `UniqueConstraint` on the triple (`alerts/models.py:47`) is the concurrency
  backstop; the store is wrapped in `transaction.atomic()` and `IntegrityError` is
  caught and treated as a duplicate (`ingestion/tasks.py:76`).
- **Every arrival** (including duplicates) writes a `DeliveryReceipt` — duplicates
  are telemetry, not noise (`ingestion/models.py:51`).

## Single entry point for all transports

MQTT, webhook, feed-poll, and manual upload all converge on
`ingest_raw_message.delay(...)`: MQTT consumer (`mqtt_consumer.py:47`), webhook view
(`ingestion/views.py:26`), feed poller (`ingestion/tasks.py:234`), backfill job.
Add new transports the same way — never fork the pipeline.

## Denormalized read model for serving

Write model (`Alert`/`AlertInfo`/`AlertArea`, immutable) is separate from the read
model (`ResolvedAlert`, one row per `EventChain`) that tiles and search query.
The lineage resolver (`alerts/lineage.py:82` `_refresh_resolved`) rebuilds
`ResolvedAlert` with denormalized filter columns, precomputed geometry
simplifications (`geom_z5`/`geom_z8`), and array columns indexed with GIN.
Expiry is a **query-time predicate** (`expires > t`), not a state mutation — this
is what makes time-travel/animation work. Search (`api/views.py:18`) and the
Martin tile SQL (`tiles/.../create_alerts_tile_function.py`) both filter
`ResolvedAlert` the same way.

## Signal → on_commit → Celery for side effects

External side effects are scheduled after the DB commit, never inline in the
signal. `sources/apps.py:15`: `post_save`/`post_delete` on `SourceAuthority` →
`transaction.on_commit(...)` → `sync_mosquitto_auth.delay()`. Guarded so it only
fires when relevant (MQTT actually in use).

## Atomic file writes for the broker mount

Files consumed by another process (Mosquitto watches its auth files) are written
write-then-rename so the watcher never sees a half-written file, with explicit
ownership handoff and a non-root dev fallback (`sources/mosquitto.py:55`).

## Settings & config

- Split settings: `base.py` + `dev.py`/`production.py` (each does
  `from .base import *`). `config/celery.py:5` defaults to the dev module.
- All config via env with typed defaults through `django-environ`
  (`base.py:11`); DB via `DATABASE_URL` (`postgis://` scheme selects PostGIS).
- Wagtail admin per app: models expose `panels`; `wagtail_hooks.py` registers a
  `SnippetViewSet`/`SnippetViewSetGroup` (`sources/wagtail_hooks.py`).

## Geometry conventions

All geometry is EPSG:4326 in storage. CAP polygon coordinate order is `lat,lon`
(note: reversed from GeoJSON) — see `alerts/parser.py:4`. Circles are buffered
geodesically via pyproj; polygons get `ST_MakeValid` fixups recorded as warnings.
Polygon→MultiPolygon normalization recurs (`lineage.py:107`, `resolver.py:35`).
