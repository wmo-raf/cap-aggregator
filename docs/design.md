# CAP Aggregator — Design Document

A CAP v1.2 alert aggregator that ingests alerts directly from **cap-composer** instances over MQTT, resolves them into
an authoritative current state, and serves them via vector tiles, search APIs, and re-publication feeds.

Target: aggregating alerts from National Meteorological and Hydrological Services (NMHSs) running
cap-composer, plus any authority exposing a CAP ATOM/RSS feed.

---

## 1. Integration with cap-composer (the core decision)

cap-composer already ships everything needed

### What cap-composer provides today

| Capability                         | Where                                     | Notes                                                                                                                 |
|------------------------------------|-------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| Publish CAP XML to any MQTT broker | `cap/mqtt/models.py` `CAPAlertMQTTBroker` | Host, port, username, Fernet-encrypted password, custom topic, QoS 0/1. `is_wis2box` is optional — plain brokers work |
| Auto-publish on alert publication  | `page_published` signal → Celery task     | Fires for `status=Actual`, `scope=Public` alerts                                                                      |
| Delivery log + operator republish  | `CAPAlertMQTTBrokerEvent`                 | PENDING/FAILURE/SUCCESS, retries, republish flow                                                                      |
| XMLDSIG signing                    | `cap/sign.py` (signxml, RSA-SHA256)       | Enveloped signature, optional per instance                                                                            |
| HTTP webhook push                  | `cap/webhook/`                            | With auth header — fallback channel                                                                                   |
| ATOM/RSS feed                      | `/api/cap/rss.xml`                        | Poll fallback for instances that can't reach the broker                                                               |
| Canonical alert XML                | `/api/cap/<uuid>.xml`                     | Stable per-alert URL                                                                                                  |

### MQTT payload contract (as published by cap-composer)

```json
{
  "data": "<base64-encoded CAP alert XML, possibly XMLDSIG-signed>",
  "filename": "Actual_20260706T120000_flood-warning-nairobi.xml"
}
```

The aggregator's consumer decodes `data` and treats the XML as the source of truth. `filename`
encodes `{status}_{sent}_{slug}` and is used only for logging.

### Onboarding an authority (operational flow)

1. Admin registers the authority in the aggregator (name, country, CAP `sender` value, contact).
2. Aggregator generates MQTT credentials and a scoped topic: `cap/in/{country_iso2}/{authority_slug}`.
3. Mosquitto's `passwd` and `acl` files sync **automatically on save** (post_save signal →
   Celery task writes the shared mount; the broker's entrypoint watches the files and SIGHUPs
   itself on change). The authority's user may **write only to its own topic**; the aggregator's
   consumer user reads `cap/in/#`. `capagg sync_mosquitto` remains for bootstrap/repair.
4. The NMHS admin adds one "MQTT Broker" entry in their cap-composer admin: aggregator host/port,
   the issued credentials, the issued topic, QoS 1, `is_wis2box` unchecked.
5. Every published Actual/Public alert now flows to the aggregator in near-real-time; the composer's
   own event log shows delivery status, and its republish button re-sends missed alerts.

### Sender verification

Because each authority writes to its own ACL-scoped topic, **topic = authenticated identity**.
The consumer additionally checks that the CAP `<sender>` matches the sender value(s) registered
for that authority; mismatches quarantine the message. XMLDSIG signatures are verified when the
authority has uploaded its certificate.

### Transport model

| Transport         | Requirement                      | Role                                                                                                                                                   |
|-------------------|----------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| **RSS/ATOM feed** | **Required** for every authority | The CAP-standard baseline. Type declared or autodiscovered (root-element sniff: `<rss>` vs Atom `<feed>`). Polled *continuously*, not just as fallback |
| **MQTT**          | Optional, **preferred**          | Near-real-time push, as above                                                                                                                          |
| **Webhook**       | Optional                         | Push fallback: `/api/ingest/webhook/{authority_token}/`                                                                                                |
| Manual upload     | —                                | Backfill/testing                                                                                                                                       |

All paths converge on one Celery task: `ingest_raw_message`.

**Adaptive polling.** The feed poller always runs, at two speeds per authority: while a push
transport is configured and healthy (a push delivery within the reconcile window), it polls at the
slow *reconcile* interval (default 30 min) purely to catch messages push missed; when push goes
quiet or none is configured, it tightens to the *fast* interval (default 5 min). Conditional GET
(ETag/Last-Modified) keeps reconcile sweeps nearly free.

### Duplicate resolution across transports (first-wins + receipts)

No transport "preference" is needed for content: CAP messages are **immutable**, identified by the
triple `(sender, identifier, sent)` — the same alert arriving via MQTT and later via the feed is
byte-for-byte-equivalent in meaning even when serialization differs (stylesheet PI, signed vs
unsigned). So:

- **First-wins**: whichever transport delivers first stores the content (in practice MQTT, by
  minutes). Later arrivals change nothing.
- **Every arrival is logged** as a `DeliveryReceipt` (authority, transport, alert, was_first,
  received_at) — duplicates are telemetry, not noise:
    - per-authority MQTT-vs-poll latency → health dashboard
    - alert arrived **only via poll** → the push transport silently failed (alert + surface it)
    - alert **never appeared in the feed** → the authority's feed is broken/incomplete
- **Two-layer dedup**: sha256 of exact bytes (fast path), then the identity triple checked before
  full processing (catches cross-transport byte differences); the DB unique constraint on the
  triple is the concurrency backstop.
- **Conflict case** (same triple, materially different content — a misbehaving publisher): keep
  the first-stored message, record the conflicting arrival, and flag it as a source-quality issue
  on the health dashboard. Never silently overwrite.

---

## 2. Architecture

```
 cap-composer #1 ─┐  MQTT (QoS 1)
 cap-composer #2 ─┼──► Mosquitto ──► mqtt-consumer ──► Redis/Celery ──► ingestion pipeline
 cap-composer #N ─┘   (cap/in/#)     (paho loop)        (capagg-        validate → parse →
 ATOM feeds ────────► Celery beat pollers ─────────────► ingestion Q)   quarantine|store →
 webhooks ──────────► Django view ─────────────────────►                lineage resolve
                                                                            │
                                          PostGIS (PostgreSQL) ◄──────────┘
                                                │
                    ┌───────────────┬───────────┼──────────────┬───────────────┐
                Martin tiles    Search/API   Histogram      Re-publication   Metrics
                alerts_tile()   (DRF)        endpoint       (ATOM/MQTT out/  (health
                                                             webhooks)        dashboard)
                                                │
                                     Vue 3 SPA in Wagtail templates
                                     (MapLibre, time slider, filters)
```

### Services (docker-compose)

| Service                   | Image / origin              | Role                                                  |
|---------------------------|-----------------------------|-------------------------------------------------------|
| `capagg-app`              | this repo                   | Django/Wagtail (admin, APIs, frontend shell)          |
| `capagg-worker-default`   | this repo                   | Celery, light tasks (`capagg-default` queue)          |
| `capagg-worker-ingestion` | this repo                   | Celery, ingestion pipeline (`capagg-ingestion` queue) |
| `capagg-beat`             | this repo                   | Celery beat (feed polling, sweeps, metrics rollups)   |
| `capagg-mqtt-consumer`    | this repo (entrypoint mode) | paho-mqtt subscriber → Celery                         |
| `capagg-mosquitto`        | `eclipse-mosquitto:2`       | Central broker, per-authority ACL                     |
| `capagg-db`               | `imresamu/postgis:18-3.6`   | Relational + spatial storage (multi-arch)             |
| `capagg-redis`            | `redis:7`                   | Celery broker/result + SSE fan-out pub/sub            |
| `capagg-martin`           | `ghcr.io/maplibre/martin`   | Vector tiles from function source                     |
| `capagg-web-proxy`        | `nginx`                     | Reverse proxy, tile cache                             |

---

## 3. Ingestion pipeline

`ingest_raw_message(source_id, transport, payload)` on the `capagg-ingestion` queue:

1. **Store raw, immutably.** Insert `RawMessage` with sha256 of the XML bytes. Duplicate hash →
   mark as duplicate, stop (idempotent across transports: the same alert arriving via MQTT and the
   RSS fallback poller lands once).
2. **XSD validation** against the CAP v1.2 schema (lxml, pre-compiled).
3. **Semantic validation** (see §7) via a pluggable validator registry.
4. **Signature verification** if `<ds:Signature>` present and the authority has a certificate.
5. **Sender verification** — CAP `sender` must match the authority bound to the topic/token.
6. **Quarantine on failure** — never silently drop. `QuarantinedMessage` stores the full
   validation report; the authority sees it (feedback loop) and can resubmit.
7. **Parse & normalize** into `Alert` / `AlertInfo` / `AlertArea` rows. Circles buffered
   server-side (geodesic) into polygons. Geocode-only areas resolved via the geocode registry.
8. **Dedup** on `(sender, identifier, sent)` — CAP's message identity triple.
9. **Lineage resolution** (§4) updates the per-event resolved state.
10. **Fan-out**: Redis pub/sub event for SSE live mode; re-publication tasks; metrics row.

Recovery: a `sweep_unprocessed` periodic task re-processes stuck `RawMessage` rows.

---

## 4. Lineage resolution

CAP chains: `Alert` → `Update`* → `Cancel`?, linked by `<references>` (`sender,identifier,sent`
triples). Design:

- Every message immutable in `Alert`; chains grouped by an `EventChain` row.
- On arrival, walk `references`: if a referenced alert exists, join its chain; else create a chain
  and record a **dangling reference** (out-of-order arrival). When the missing alert later arrives,
  dangling references re-resolve and chains merge.
- `ResolvedAlert` = one row per chain holding the *effective current state*: latest non-cancelled
  content, denormalized filter columns (severity, urgency, certainty, category, event, msg_type,
  status, language, onset/effective/expires), country attribution, and simplified geometries at
  3 tolerances for tile serving.
- `Cancel` marks the chain cancelled (kept, flagged — cancellations are renderable history).
- Expiry is a query-time predicate (`expires > t`), not a state mutation — this is what makes
  time-travel/animation work.
- All tiles and search serve `ResolvedAlert` by default; raw messages remain queryable
  (`?resolved=false`).

Edge cases: references to alerts never received (chain starts at the Update; flag
`incomplete_chain`), cross-transport duplicates (hash + identity dedup), same event re-issued as
a new chain (no reference) — left as separate chains, optionally linked by a heuristic
(same sender+event+overlapping area/time) surfaced in the lineage viewer, never auto-merged.

---

## 5. Storage schema (PostGIS)

Django apps → tables (all geometry EPSG:4326):

**sources**

- `SourceAuthority` — name, slug, country (ISO 3166-1 a2), CAP sender values (array), contact,
  cert (PEM, optional), **required feed** (URL, type declared/autodetected, fast + reconcile poll
  intervals, ETag/Last-Modified state), optional `mqtt_username`/`mqtt_password_hash`/`mqtt_topic`,
  optional webhook token, active.

**ingestion**

- `RawMessage` — authority FK, transport (mqtt/webhook/poll/manual), topic, xml (text),
  sha256 (unique), received_at, sent_at (from CAP, for latency), state machine
  (received→validated→stored / quarantined / duplicate).
- `QuarantinedMessage` — raw FK, report JSONB (per-check results), status
  (pending/notified/resubmitted/dismissed).
- `DeliveryReceipt` — authority FK, transport, alert FK, raw FK, `was_first`, received_at. One row
  per arrival per transport, including duplicates (see §1 duplicate resolution).

**alerts**

- `Alert` — authority FK, raw FK, identifier, sender, sent, msg_type, status, scope,
  references JSONB, code/note, signature_valid (nullable bool), unique `(sender, identifier, sent)`.
- `AlertInfo` — alert FK, language, categories (array), event, response_types (array), urgency,
  severity, certainty, audience, onset/effective/expires, sender_name, headline, description,
  instruction, web, contact, parameters JSONB, event_codes JSONB. Full-text search vector on
  headline+description.
- `AlertArea` — info FK, area_desc, geom (MultiPolygon), is_circle_derived, altitude/ceiling,
  geocodes JSONB (scheme→values).
- `EventChain` — authority FK, first/latest alert FKs, is_cancelled, incomplete_chain.
- `ResolvedAlert` — chain OneToOne; denormalized filter columns; `geom`, `geom_z5`, `geom_z8`
  (ST_SimplifyPreserveTopology); `centroid`; `countries` (array, from geometry ∩ admin-0);
  GIST indexes on geoms, btree on (effective, expires), GIN on categories/countries.

**geocodes**

- `GeocodeScheme` (EMMA_ID, ISO 3166-2, FIPS, national schemes) and `GeocodeValue` — scheme FK,
  value, name, geom, `valid_from`/`valid_to` (admin boundaries change; versioned). Resolution
  picks the version valid at the alert's `sent` time.
- Admin boundaries via `django-adminboundarymanager` (as used by cap-composer) for country
  attribution and drill-down.

**metrics** (plain time-indexed tables)

- `ingest_metrics(time, authority_id, transport, latency_s, outcome)` — powers the health
  dashboard; hourly/daily rollups via a periodic Celery task into a summary table (or a
  materialized view).
- `alert_activity(time, authority_id, severity, count)` — powers the histogram endpoint cheaply
  (`count(*) GROUP BY date_trunc(...)` over an indexed time column).
- Retention: nightly Celery task deletes rows past the retention window.

Raw XML lives in Postgres (text) initially — volumes are small (alerts, not rasters). MinIO can be
added later behind a storage-manager abstraction if archive volume demands it.

---

## 6. Serving

### Vector tiles (Martin function source)

One function serves everything:

```
GET /tiles/alerts/{z}/{x}/{y}
    ?t=2026-07-06T12:00:00Z        -- point in time (default: now, rounded to 5-min bucket)
    &severity=Severe,Extreme       -- optional CSV filters on resolved state
    &urgency=&certainty=&category=&msg_type=&status=&country=&event=
```

`capagg_alerts_tile(z, x, y, query_params json)` selects from `ResolvedAlert` where
`tstzrange(effective, expires) @> t` plus filters, chooses `geom_z5/geom_z8/geom` by zoom, and
returns `ST_AsMVT` with two layers: `alerts` (fills) and `alert_centroids` (symbols at low zoom).
Styling is entirely client-side via MapLibre data-driven expressions — one tileset serves every
severity/urgency/certainty variant. Animation = the client stepping `t`; rounding `t` to 1-minute
buckets makes tile URLs cacheable (nginx proxy cache, CDN later). Deep-history scrubbing can later
switch to nightly PMTiles snapshots.

### APIs (DRF + drf-spectacular)

- `GET /api/search/` — country, severity, urgency, certainty, category, event, msg_type, status,
  language, bbox, time interval, full-text `q`; paginated GeoJSON or JSON.
- `GET /api/alerts/{id}/` — resolved detail; `/api/alerts/{id}/lineage/` — full chain;
  `/api/alerts/{id}.xml` — original signed XML.
- `GET /api/histogram/` — counts per time bucket (from `alert_activity`), powers the slider's
  density waveform.
- `GET /api/stats/` — per-authority/per-country analytics; latency; quality scores.
- `GET /api/events/stream/` — SSE (Redis pub/sub) pushing alert ids for live mode; client
  refreshes affected tiles.
- `GET /api/jobs/` — async job status/progress (django-task-ferry, Celery executor on the
  ingestion queue) for long-running operations like bulk backfills and geocode imports.
- OGC API Features — phase 2, over `ResolvedAlert` (standards compliance for institutional users).

### Re-publication (aggregator as infrastructure)

- Filtered ATOM feeds: `/feeds/atom/?country=KE&severity=Severe` (any search filter).
- MQTT re-broadcast on `cap/out/{country}/{severity}` — downstream consumers subscribe with a
  read-only account; Mosquitto ACLs again.
- Webhook subscriptions per saved filter (Wagtail-managed model, Celery delivery with retries —
  cap-composer's webhook module is the template).

---

## 7. CAP validation

Layered, each check recorded in the quarantine report:

1. **Schema**: CAP v1.2 XSD (lxml, compiled once per worker).
2. **Signature**: XMLDSIG verify (signxml) when present; policy per authority —
   `require | verify_if_present | ignore`.
3. **Identity**: sender matches registered authority; `sent` not in the future (> small skew);
   dedup triple.
4. **Semantics** (pluggable registry, each rule → error or warning):
    - `expires` present and > `effective`/`onset` (MeteoAlarm profile expects expires)
    - Update/Cancel must carry `<references>`; referenced identity well-formed
    - At least one `<info>`; urgency/severity/certainty from valid enums (XSD covers, re-checked
      for clearer messages)
    - `<area>` present for Actual+Public; polygons: ≥4 points, closed ring, lon/lat sanity,
      `ST_MakeValid` fixups recorded as warnings; circles: valid radius
    - Geocodes resolvable in the registry (warning + area kept if polygon also present; error if
      geocode was the only geometry)
    - Multi-`info` language blocks: consistent event across languages (warning)
5. **Profile packs** (optional per authority): WMO CAP profile, MeteoAlarm-style constraints —
   same registry, toggled per source.

Errors → quarantine; warnings → stored with the alert and surfaced in the health dashboard
(per-source quality score = weighted error/warning rates).

---

## 8. Admin (Wagtail)

Wagtail 7 admin with per-app `wagtail_hooks.py` (cap-composer convention):

- **Authority registry** — CRUD + "issue MQTT credentials" action (generates password, shows
  one-time secret, renders copy-paste instructions for the NMHS's cap-composer broker form);
  `sync_mosquitto` management command regenerates `passwd`/ACL and HUPs the broker.
- **Quarantine inbox** — filterable list, per-message validation report, actions: notify authority
  (email with report), re-run validation (task-ferry `quarantine_revalidation` job with live
  progress), dismiss. Badge count in the admin menu.
- **Ingestion monitor** — RawMessage list with state, transport, latency; republish/reprocess.
- **Geocode registry** — schemes, versioned values, bulk import (task-ferry `geocode_import` job:
  GeoJSON or CSV+WKT, with geometry-change versioning), resolution test tool.
- **Backfill** — upload a CAP .xml or .zip archive (task-ferry `cap_backfill` job); every alert
  runs through the normal pipeline, so dedup/validation/lineage apply.
- **Re-publication** — outbound webhook subscriptions, feed definitions, MQTT out-topics.
- **Settings** — site settings for map defaults, severity colors (MeteoAlarm conventions),
  retention policy.
- **Reports** — Wagtail report pages backed by the metrics hypertables (per-authority uptime,
  latency percentiles, expired-but-never-cancelled counts).

---

## 9. Frontend

Vue 3 SPA(s) mounted in Wagtail templates: Wagtail serves the page shell + CMS-managed content;
Vite builds the app bundles; MapLibre GL JS renders tiles from Martin. Public templates follow
consistent conventions (`extra_css`/`extra_js` blocks, CSS variables, no inline styles).

Pages:

> **Amendment (frontend v1, 2026-07):** the site home is a Wagtail *landing
> page* (hero + CTA, stats strip, latest alerts — `home.HomePage`), not the map
> explorer. The explorer lives at `/explorer/` with Map/Table/Authorities/Notify
> views. See PRD issue #38.

1. **Map explorer (home)** — MapLibre map, filter panel (country, severity, urgency, certainty,
   category, event type, msg_type, language), time slider with histogram density waveform, play/
   pause animation stepping `t`, live mode toggle (SSE), severity legend (MeteoAlarm colors),
   alert popup → detail.
2. **Alert detail** — full multi-language CAP rendering (language tabs), area map, lineage
   timeline (Alert → Update → Cancel visualization), links to raw signed XML, share/embed.
3. **Country page** — drill-down: active alerts, history sparkline, authority info, country feed
   URLs.
4. **Source health dashboard** — per-authority cards: last alert, feed latency (sent vs received),
   validation error rate, expired-never-cancelled count, uptime. The "WIS2Watch for CAP" view —
   likely the highest-value screen for WMO.
5. **Archive/search** — table + map results for historical queries.
6. **Integrations page** — self-service docs: feed URLs per filter, MQTT out-topics, webhook
   subscription info, embed snippet generator.
7. **Embeddable widget** — tiny MapLibre bundle at `/embed/?country=KE`, iframe-safe, for NMHS
   sites (ClimWeb).

Phase-2 extras: population under alert (WorldPop zonal statistics against alert polygons; live
exposed-population counter during animation).

---

## 10. Stack summary

| Concern   | Choice                                                                                         |
|-----------|------------------------------------------------------------------------------------------------|
| Framework | Django 5 + Wagtail 7                                                                           |
| DB        | PostgreSQL 18 + PostGIS 3.6 (`imresamu/postgis:18-3.6`, multi-arch), app traffic via PgBouncer |
| Queue     | Celery + Redis (`capagg-default`, `capagg-ingestion`)                                          |
| MQTT      | Mosquitto 2 (per-authority ACL); paho-mqtt consumer service                                    |
| Tiles     | Martin function source (`capagg_alerts_tile`)                                                  |
| Frontend  | Vue 3 + Vite + MapLibre, mounted in Wagtail templates                                          |
| API       | DRF + drf-spectacular                                                                          |
| Packaging | uv, `pyproject.toml`                                                                           |
| Deploy    | docker-compose + nginx (tile cache)                                                            |

## 11. Phasing

1. **MVP ingest**: Mosquitto + consumer + validation + quarantine + Alert/Info/Area storage;
   authority registry + credential provisioning; one composer instance publishing end-to-end.
2. **Resolve & serve**: lineage resolver, ResolvedAlert, Martin tile function, search + histogram
   APIs, map explorer with time slider.
3. **Trust & feedback**: signature verification, quarantine notification workflow, health
   dashboard, metrics hypertables.
4. **Infrastructure**: re-publication (ATOM/MQTT out/webhooks), embed widget, OGC API Features,
   PMTiles archive, population under alert.

## 12. Open questions (carried forward)

- **Decided**: broker auth via passwd/ACL files, auto-synced on SourceAuthority save with broker
  self-reload. Fine to ~hundreds of authorities. Revisit (dynamic-security plugin over `$CONTROL`
  topics, or EMQX) only if credential count/churn outgrows the file model.
- **Decided**: PostGIS-only. Alert and telemetry volumes (~low millions of rows/year) don't need
  time-series partitioning. If the archive ever gets heavy, use native Postgres declarative
  partitioning on `Alert.sent`.
- Geocode registry sourcing per country; fallback when a geocode cannot be resolved and no
  polygon is present.
- Country attribution: sender authority vs geometry intersection — current design stores **both**
  (`authority.country` + `ResolvedAlert.countries[]`); UI presents cross-border alerts under every
  intersected country with an "issued by" badge.
- Retention: raw XML kept indefinitely (small); resolved-state history partitioning once volume
  is known.
- Multi-language search ranking; Accept-Language selection for default info block.
- Tile bucket size (5 min) vs animation smoothness — revisit with real data.
