# Roadmap: making CAP Aggregator usable

Two milestones, in order:

- **Phase B — Operator-usable.** An operator can onboard a source and *trust*
  that alerts are flowing, validated, and recoverable — running unattended, with
  no shell access required. The ingestion half of the system is already real
  (pipeline, validation, lineage → `ResolvedAlert`, Martin tile function); B is
  mostly *wiring it to run on its own* and *surfacing it in the admin*.
- **Phase A — Public-usable.** Someone opens a web page, sees current alerts on a
  map, filters them, and clicks one for detail. This is the product's reason to
  exist and requires building the frontend, which today is **zero** (the `home`
  app isn't even installed; `static/frontend/map-explorer.js` is a 3-line stub).

Decisions below were resolved in a design interview; each notes what was
explicitly **deferred** so scope stays honest.

---

## Phase B — Operator-usable

### B1. Autonomous ingestion (scheduling)

**Problem:** `CELERY_BEAT_SCHEDULE = {}` (`config/settings/base.py:209`) and the
project uses `django_celery_beat`'s `DatabaseScheduler` — so `poll_all_feeds` and
`sweep_unprocessed` (`ingestion/tasks.py:159`, `:142`) never fire. Nothing runs
periodically; a registered authority ingests nothing.

**Do:**
- Populate `CELERY_BEAT_SCHEDULE` with two entries:
  - `poll_all_feeds` every **60s**
  - `sweep_unprocessed` every **300s**
- `DatabaseScheduler` syncs these into editable `PeriodicTask` rows on beat
  startup, so operators can still pause/retune them, but a fresh `make dev-up`
  works with no manual admin step.

`poll_all_feeds` already checks each authority's `feed_last_polled` against its
adaptive interval and only fans out `poll_feed` for due ones — beat just needs to
tick it; the task decides who's due.

**Acceptance:** register an authority with a live CAP RSS URL, wait one poll
cycle, and see `RawMessage`/`ResolvedAlert` rows appear with no manual trigger.

### B2. Non-blocking onboarding (fix `clean()`, drop dead config)

**Problem:** `SourceAuthority.clean()` (`sources/models.py:145`) does a
synchronous `autodiscover_feed_type` HTTP fetch (up to 15s) on every admin save,
hanging or erroring the form if the feed is slow/down. And it's pointless:
`fetch_feed` uses `feedparser.parse()`, which auto-detects RSS vs Atom
(`feeds.py:56`) — nothing in the polling path reads `feed_type`. The field only
decorates an admin list column.

**Do:**
- Remove the network call from `clean()`; keep only cheap local validation
  (URL present, `sender_values` non-empty).
- Detect the type opportunistically inside `poll_feed` (the feed is already being
  fetched there) and store it for display; `effective_feed_type`'s job disappears.
- **Delete the dead machinery:** `feed_type`, `feed_type_detected`, `FEED_TYPES`,
  `effective_feed_type` (`models.py`), `autodiscover_feed_type` (`feeds.py`), the
  `effective_feed_type` entry in `list_display` (`sources/wagtail_hooks.py:21`),
  plus a migration to drop the two columns.

**Acceptance:** saving an authority whose feed URL is currently unreachable
succeeds instantly; the type still shows up after the first successful poll.

### B3. MQTT credential issuance (admin action)

**Problem:** `issue_mqtt_credentials()` (`models.py:179`) exists but is
shell-only; the MQTT fields are `editable=False`, so they can't live in the edit
form. No operator UX.

**Do:**
- Add a Wagtail snippet action **"Issue / regenerate MQTT credentials"** on
  `SourceAuthority` → a dedicated **result page** showing:
  - username, the **plaintext password rendered once** (held in memory only,
    never stored or re-shown),
  - the topic (`cap/in/{country}/{slug}`),
  - a **copy-paste cap-composer broker block** (host, port, QoS 1,
    `is_wis2box` unchecked).
- **Regenerate overwrites** the stored hash (old password stops working after the
  next broker sync); no dual-key grace window — fine at the design's
  "~hundreds of authorities" scale.
- Add a **"credentials issued ✓/✗" indicator** to the snippet list/detail.
- Issuance calls `save(update_fields=[...])`, whose `post_save` signal already
  fires `sync_mosquitto_auth` (`sources/apps.py:15`) — no extra wiring.

**Deferred:** surfacing **broker-sync status** (did the broker actually reload the
`passwd`/`acl` files). "Issued" won't yet guarantee "broker accepted it."

**Acceptance:** an operator issues credentials from the admin, copies the shown
password + broker block, and a cap-composer instance connects and publishes to
its topic successfully.

### B4. Quarantine inbox (admin)

**Problem:** invalid alerts are stored in `QuarantinedMessage` with a full
`report` (`ingestion/models.py:83`) but nothing surfaces them.

**Do:** a Wagtail list view (per-app `wagtail_hooks.py` convention) with:
- filterable list of quarantined messages,
- a **rendered validation report** per message (the per-check errors/warnings),
- a **"re-run validation" action** wired to the existing
  `QuarantineRevalidationJobType` (`ingestion/job_types.py:70`), linking to its
  task-ferry progress at `/api/jobs/<id>/`,
- a **dismiss** action.

**Deferred:** the **"notify authority" email** (emailing the report to
`contact_email`) — needs email templating; ships with the health dashboard later.

**Acceptance:** feed a deliberately-bad CAP file (e.g. sender not in
`sender_values`); it appears in the inbox with a legible reason; fixing the
authority + re-validating moves it to stored.

### B5. Ingestion monitor (admin)

**Do:** a read-oriented Wagtail list of `RawMessage` showing state, transport,
and received-vs-sent latency (`received_at` − `sent_at`), filterable by
state/transport/authority. Gives the operator "alerts are landing" visibility.

**Deferred:** the **health dashboard** — per-authority MQTT-vs-poll latency,
"arrived only via poll → push silently failed" detection, error rates, uptime.
This is the design's Phase-3 "WIS2Watch for CAP" screen; it needs aggregation
plumbing (and arguably the `alert_activity`/metrics tables, which don't exist).
The `DeliveryReceipt` history keeps accruing so it can be built on real data later.

### B6. Manual backfill / CAP upload (admin)

**Problem:** `CapBackfillJobType` (`ingestion/job_types.py:23`) already ingests a
`.xml` or `.zip` through the full pipeline (dedup/validate/quarantine/lineage all
apply) with task-ferry progress — but has no admin entry point.

**Do:** a **thin** upload action — single file field → save upload to a path →
`JobHandler.create_and_start(user, "cap_backfill", authority_id=..., file_path=...)`
→ link to the job-progress endpoint. Doubles as the integration-test harness and
lets you demo the whole pipeline without a live source.

**Acceptance:** upload a sample CAP file and watch it flow validate → store →
resolve → appear in the (Phase-A) tiles.

### B — suggested order

`B1` (unblocks everything) → `B2` (unblocks clean onboarding) → `B6` (gives you a
data source to test the rest without a live feed) → `B4` + `B5` (visibility) →
`B3` (MQTT issuance). B3 last because feed-only onboarding is already usable once
B1/B2 land, so the push path is the enhancement, not the blocker.

---

## Phase A — Public-usable (the map)

> **Frontend architecture — the one real divergence from `docs/design.md`, flag
> if you disagree.** The design commits to a **Vue 3 + Vite + MapLibre** SPA, but
> there is no frontend, no Vite, no node toolchain in the image today. For the
> *first* usable public view I recommend a **no-build vanilla MapLibre page**
> (plain JS + a MapLibre CDN/vendored bundle, rendered by a Wagtail template) and
> deferring the Vue/Vite SPA until interactivity (time slider, live mode, complex
> filter state) actually justifies a build step. This removes an entire
> build-toolchain workstream from the critical path to "there is a working map."
> If you'd rather stand up Vue+Vite now, that's a legitimate call — it just
> front-loads setup cost.

### A1. Serving foundations (APIs + page shell)

These are prerequisites the map/detail views consume:

- **Register the `home` app** (add `capaggregator.home` to `INSTALLED_APPS`) and
  create a Wagtail `HomePage(Page)` model + template to own `/`. Note Wagtail's
  initial page-tree bootstrap (a data migration to create/promote the HomePage).
- **Auto-create the Martin tile function on deploy.** `capagg_alerts_tile()`
  exists as a management command (`tiles/.../create_alerts_tile_function.py`) but
  is manual. Call it from the app entrypoint after `migrate`, or via a `tiles`
  data migration, so a fresh environment serves tiles with no manual step.
- **Alert detail API** — `GET /api/alerts/{id}/`: a `RetrieveAPIView` +
  `ResolvedAlertDetailSerializer` returning the resolved state, all language
  `AlertInfo` blocks, and area GeoJSON. Needed for click → detail.
- **Lineage API** — `GET /api/alerts/{id}/lineage/`: the chain's alerts ordered by
  `sent` (Alert → Update → Cancel) for the detail timeline.
- **Populate `search_vector`.** The field + GIN index exist (`alerts/models.py:79`)
  but nothing writes them, so full-text can't work. Populate in `parse_and_store`
  (a post-insert `SearchVector('headline','description')` update) or via a DB
  trigger. Wire the existing `q` TODO in `AlertSearchView` (`api/views.py:54`).
  *(Full-text UI itself is A-later; do the population now so it's ready.)*

### A2. Map explorer MVP

A single MapLibre page (per the frontend note above) that delivers the core loop:

- Render `alerts` + `alert_centroids` layers from Martin
  (`/tiles/alerts/{z}/{x}/{y}`), **severity-colored client-side** via data-driven
  expressions (MeteoAlarm palette) — one tileset serves every variant.
- **Filter panel:** country, severity, urgency, certainty, category, event,
  msg_type, status — passed as tile query params (the tile function already
  supports all of them) and to `/api/search/`.
- **Click → popup → detail** using the A1 detail API.
- Point-in-time = **current alerts** (default `t = now`).

**Acceptance:** with real data from B, a visitor sees current alerts on the map,
narrows by severity + country, and opens one for its details.

### A3. Alert detail view

Multi-language CAP rendering (language tabs), an area map, and the lineage
timeline (Alert → Update → Cancel), from the A1 detail + lineage APIs. Can be a
Wagtail-templated page or a modal fed by the API.

### A — deferred to A-later (design Phase 2 tail / Phase 4)

Time slider + **histogram API** (`api/views.py:58` is a `501` stub; needs an
`alert_activity`-style aggregation) + play/pause animation; **live SSE mode**
(`event_stream` works but needs ASGI in prod, `views.py:64`); **full-text search
UI**; country pages; embeddable widget; re-publication (filtered ATOM out, MQTT
`cap/out/*`, webhook subscriptions); country-intersection attribution
(`lineage.py:147` `_attribute_countries` currently returns only the issuing
authority's country); the **Vue/Vite SPA migration** if/when interactivity grows.

---

## Cross-cutting deferrals (explicitly out of B and first-A)

- Health/monitoring dashboard + metrics tables (`alert_activity`, ingest metrics).
- Notify-authority email workflow.
- Broker-sync status surfacing.
- Time-travel/animation, live mode, full-text UI, re-publication, embed widget.
- Country attribution via admin-0 geometry intersection.
