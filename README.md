# CAP Aggregator

> [!WARNING]
> **Under active development.** This project is not ready for production use — APIs, data
> models, and configuration may change without notice.

Aggregates CAP v1.2 alerts from many [cap-composer](https://github.com/wmo-raf/cap-composer)
instances (and any CAP ATOM/RSS feed) into one authoritative, queryable, visual platform.

- **Push-first ingestion**: each cap-composer instance publishes to this aggregator's Mosquitto
  broker over MQTT
- **Validation + quarantine**: CAP 1.2 XSD, semantic rules, XMLDSIG verification; invalid alerts
  are quarantined with a report
- **Lineage resolution**: Alert → Update → Cancel chains resolved into effective current state
- **PostGIS** storage; **Martin** vector tiles with time + filter parameters
- **MapLibre frontend** with time-slider animation and rich filtering (Vue 3 in Wagtail)
- **Re-publication**: filtered ATOM feeds, MQTT re-broadcast, webhook subscriptions

See [docs/design.md](docs/design.md) for the full design.

## Quick start (dev)

```bash
cp .env.sample .env          # edit values (at least DB_PASSWORD, SECRET_KEY)
docker network create climtech # shared external network (once; override via NETWORK_NAME)
make dev-build
make dev-up                  # foreground; use dev-up-d for detached
make dev-createsuperuser
```

App: http://localhost:8000 (admin at /admin). Martin: http://localhost:3000.
The dev overlay (`docker-compose.dev.yml`) mounts `./src` with hot reload —
Django autoreloads and Celery workers restart on file changes (watchmedo). Migrations run
automatically on app start.

Production: `make build && make up` — gunicorn, no source mounts, nginx serves static/media
on `WEB_PORT`.

Services: Django/Wagtail app, Celery workers (default + ingestion), Celery beat, MQTT consumer,
Mosquitto, PostGIS, Redis, Martin, nginx. All state lives in `./docker-data/`.

## Connecting a cap-composer instance

1. In this aggregator's admin, create a **Source Authority** with its CAP RSS/ATOM feed URL
   (**required** — e.g. `https://<composer>/api/cap/rss.xml`; type is autodiscovered). Polling
   starts immediately.
2. Optionally (preferred) issue MQTT credentials — the broker's passwd/ACL files sync
   automatically on save and Mosquitto reloads itself
3. In the cap-composer admin (Settings → MQTT Brokers), add a broker with the aggregator's
   host/port, the issued username/password and topic (`cap/in/{country}/{authority}`), QoS 1,
   and leave "Is WIS2Box Node" unchecked.

Alerts then arrive via MQTT in near-real-time; the feed keeps being polled as a slow
reconciliation sweep (catching anything push missed), speeding up automatically if MQTT goes
quiet. Duplicates across transports are resolved first-wins on the CAP identity triple and logged
as delivery receipts for the health dashboard.

## Repository layout

```
src/capaggregator/
├── config/        # settings (base/dev/production), urls, celery
├── sources/       # SourceAuthority registry, MQTT credential provisioning
├── ingestion/     # raw messages, validation, quarantine, MQTT consumer, feed pollers
├── alerts/        # Alert/AlertInfo/AlertArea, EventChain, ResolvedAlert, lineage resolver
├── geocodes/      # versioned geocode registry (EMMA_ID, ISO 3166-2, national schemes)
├── tiles/         # Martin function source management command
├── api/           # search, histogram, stats, SSE stream
└── home/          # Wagtail pages + Vue SPA shell templates
```
