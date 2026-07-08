# CLAUDE.md

## Project overview

**CAP Aggregator** ingests CAP v1.2 emergency alerts from many
[cap-composer](https://github.com/wmo-raf/cap-composer) instances (National
Meteorological & Hydrological Services) and any CAP ATOM/RSS feed, resolves them
into one authoritative current state, and serves them as vector tiles, search
APIs, and re-publication feeds. Target users: WMO and NMHSs.

Pipeline in one line: *authorities publish CAP over MQTT (or feed/webhook) →
validate + quarantine → parse & store immutably → resolve Alert/Update/Cancel
lineage → serve resolved state via Martin tiles + DRF APIs + a Vue/MapLibre map.*

> **Status: early active development.** Much of `docs/design.md` is the target
> design; some pieces (histogram API, health dashboard, full-text search,
> country-intersection attribution, frontend pages) are stubs or TODOs. Check the
> actual code before assuming a feature exists — read the design doc for intent,
> the source for reality.

## Tech stack

- **Python ≥3.12**, **Django 5** + **Wagtail 7** (admin surface)
- **PostgreSQL 18 + PostGIS 3.6** — all geometry EPSG:4326
- **Celery + Redis** — queues `capagg-ingestion` (heavy) and `capagg-default`
- **Mosquitto 2** (MQTT broker) + a **paho-mqtt** consumer service
- **Martin** vector tiles from a PostGIS function source
- **DRF + drf-spectacular** (REST API), **django-task-ferry** (async jobs w/ progress)
- **lxml** (XSD/parse), **signxml** (XMLDSIG), **shapely/pyproj** (geometry)
- **Vue 3 + MapLibre** frontend mounted in Wagtail templates
- **uv** for packaging (`pyproject.toml`), **ruff** for lint (line length 120)
- Deployed via **docker-compose** + nginx (tile cache)

## Key directories

All Python lives in `src/capaggregator/`. Each app is a bounded context with a
short DB label (`capagg_*`); cross-app FKs reference by that label string.

- `config/` — settings (`base`/`dev`/`production`), root urls, celery app
- `sources/` — `SourceAuthority` registry, MQTT credential provisioning, Mosquitto
  auth-file sync, feed fetching/autodiscovery
- `ingestion/` — the pipeline: `RawMessage`, `DeliveryReceipt`, `QuarantinedMessage`,
  validators, MQTT consumer command, webhook view, feed pollers, task-ferry jobs
- `alerts/` — core CAP storage (`Alert`/`AlertInfo`/`AlertArea`), `EventChain` +
  `ResolvedAlert` (denormalized read model), the XML parser, lineage resolver
- `geocodes/` — versioned geocode registry + resolver (schemes valid at alert time)
- `tiles/` — management command that creates the `capagg_alerts_tile()` Martin function
- `api/` — DRF search, histogram, SSE live stream
- `home/` — Wagtail pages + Vue SPA shell

## Build / test / run

Everything runs in Docker via the `Makefile` (dev overlay mounts `./src` with hot
reload; migrations run automatically on app start). The console script is `capagg`
(= `manage.py`).

```bash
cp .env.sample .env         # set at least SECRET_KEY, DB_PASSWORD
make dev-build
make dev-up                 # foreground (dev-up-d for detached)
make dev-createsuperuser
make dev-test               # pytest inside the app container
make dev-shell              # bash in the app container
make dev-migrate            # or dev-makemigrations
make dev-create-tile-function   # (re)create the Martin tile function
make dev-app-logs           # also dev-worker-{default,ingestion}-logs, dev-consumer-logs
```

App at http://localhost:8000 (admin `/admin`, health `/health/`); Martin at :3000.
Production targets (`make build && make up`) run gunicorn with no source mounts.
Run `ruff check src/` for lint. Mosquitto auth syncs automatically on authority
save — `make dev-sync-mosquitto` is only for bootstrap/repair.

## Additional documentation

Check these when the task touches the relevant area:

- **[.claude/docs/architectural_patterns.md](.claude/docs/architectural_patterns.md)**
  — Read before adding tasks, validators, jobs, models, or pipeline logic. Covers
  the Celery task conventions, reusable-pipeline pattern, validator/job registries,
  immutable-store-first dedup + receipts, single transport entry point, the
  denormalized `ResolvedAlert` read model, signal→on_commit→Celery side effects,
  and geometry conventions.
- **[.claude/docs/template_conventions.md](.claude/docs/template_conventions.md)**
  — Read before editing any Django/Wagtail HTML template. Markup/JS conventions
  (no inline styles, `extra_css`/`extra_js` blocks, `const`/`let`, DOMContentLoaded
  over IIFEs) and which CSS custom-property tokens to use per context (`--w-color-*`
  in admin, our own `--color-*` in the frontend — never mix them).
- **[docs/design.md](docs/design.md)** — full system design and rationale
  (transport model, lineage resolution, storage schema, serving, validation
  layers, admin, frontend, phasing, open questions). The source of *intent*; parts
  are still aspirational.
- **[README.md](README.md)** — quick start and how an NMHS connects a cap-composer
  instance (creating a Source Authority, issuing MQTT credentials).
