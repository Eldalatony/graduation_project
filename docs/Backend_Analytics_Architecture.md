# SHEMMS — Backend & Analytics Architecture Reference

A complete walkthrough of the backend (Node.js/Express) and analytics
(Python/Flask) services: every file, every endpoint, every collection, and
how data flows from a smart plug all the way to the dashboard chart.

---

## Table of contents

1. [System overview](#1-system-overview)
2. [Data stores and what each one holds](#2-data-stores-and-what-each-one-holds)
3. [Backend folder reference](#3-backend-folder-reference)
4. [Analytics folder reference](#4-analytics-folder-reference)
5. [End-to-end data pipeline](#5-end-to-end-data-pipeline)
6. [Endpoint reference](#6-endpoint-reference)
7. [Connection diagram](#7-connection-diagram)
8. [Scenarios — what happens when…](#8-scenarios--what-happens-when)
9. [Operations & runbook](#9-operations--runbook)

---

## 1. System overview

SHEMMS is split into 5 services that all live in the same docker-compose
network:

| Service | Stack | Port | Public? | Purpose |
|---|---|---|---|---|
| `frontend` | Next.js | 3000 | yes | User dashboard |
| `backend` | Node.js / Express | 3001 | yes | API gateway, ingestion, real-time alerts |
| `analytics` | Python / Flask | 5000 | yes (debug only) | ML, aggregations, HE demo |
| `simulator` | Python | — | no | Fake smart plugs for development |
| `mosquitto` | Eclipse MQTT | 1883 | yes | Message broker |
| `postgres` | PostgreSQL 15 | 5432 | yes | Users, appliances, schedules, real-time alerts |
| `influxdb` | InfluxDB 2.7 | 8086 | yes | Time-series readings (encrypted) |
| `mongodb` | Mongo 7 | 27017 | yes | Hourly aggregates + ML inputs/outputs |

**Frontend never talks to analytics directly.** All client traffic goes
through the backend, which proxies to analytics over the internal Docker
network.

---

## 2. Data stores and what each one holds

### PostgreSQL (`shemms` database)

Source of truth for the relational world: users, devices, schedules, alerts.
Schema in `postgres/init/init.sql`.

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Account + tariff rate | `id` UUID, `email`, `password_hash`, `tariff_rate` |
| `appliances` | Physical smart plugs | `id` UUID, `user_id`, `name`, `node_key`, `gateway_id`, `is_active` |
| `schedules` | Cron-driven on/off rules | `appliance_id`, `action`, `cron_expression`, `is_enabled` |
| `alerts` | Real-time rule-based alerts (left-on, high-usage, offline) | `user_id`, `appliance_id`, `type`, `message`, `is_read` |

### InfluxDB (`energy_data` bucket)

Every individual reading from MQTT, AES-GCM encrypted at field level.
Measurement: `appliance_readings`.

Tags (indexed): `user_id`, `appliance_id`, `gateway_id`, `node_key`.
Fields (encrypted): `power_W_enc`, `current_A_enc`, `energy_kWh_enc`, `cost_EGP_enc`.
Field (plain): `voltage_V`, `status`.

### MongoDB (`shemms` database)

Two distinct domains share this DB:

| Collection | Owner | Plaintext? | Purpose |
|---|---|---|---|
| `appliance_history` | Backend ETL | No (AES-GCM) | Hourly aggregates for backend-side querying |
| `appliance_data` | Backend ETL | Yes | Hourly aggregates for analytics ML input |
| `anomaly_alerts` | Analytics inference | Yes | Output of Isolation Forest scoring |
| `infer_checkpoint` | Analytics inference | Yes | "Last interval scored" pointer for incremental runs |

**Why two aggregate collections?** `appliance_history` is encrypted because
the backend roadmap calls for it. `appliance_data` is plaintext because the
analytics service needs raw values to train ML models — and analytics is a
trusted internal service that never directly serves a client.

---

## 3. Backend folder reference

```
backend/
├── Dockerfile
├── package.json
├── .env / .env.example
└── src/
    ├── app.js                      ← entry point
    ├── config/
    │   └── db.js                   ← PostgreSQL pool
    ├── middleware/
    │   └── authMiddleware.js       ← JWT `protect` middleware
    ├── models/
    │   ├── applianceHistory.js     ← Mongoose: encrypted hourly aggregates
    │   └── applianceData.js        ← Mongoose: plaintext analytics input
    ├── controllers/
    │   ├── authController.js       ← signup / login
    │   ├── userController.js       ← profile / tariff
    │   ├── applianceController.js  ← register / list / toggle
    │   ├── scheduleController.js   ← cron-driven on/off
    │   └── alertController.js      ← list / mark read
    ├── routes/
    │   ├── authRoutes.js           ← /api/auth/*
    │   ├── userRoutes.js           ← /api/users/*
    │   ├── applianceRoutes.js      ← /api/appliances/*
    │   ├── scheduleRoutes.js       ← /api/schedules/*
    │   ├── alertRoutes.js          ← /api/alerts/*
    │   └── analyticsRoutes.js      ← proxy to analytics
    └── services/
        ├── eventBus.js             ← internal pub/sub
        ├── mqttService.js          ← MQTT subscribe + per-reading dispatch
        ├── metricsService.js       ← derive current/voltage/kWh/cost from W
        ├── influxService.js        ← write encrypted readings, query aggregates
        ├── heService.js            ← AES-256-GCM helpers
        ├── etlService.js           ← hourly ETL: Influx → Mongo (both collections)
        ├── alertService.js         ← real-time rule alerts (high usage, left on, offline)
        ├── applianceRegistry.js    ← in-memory cache of Postgres `appliances` table
        ├── schedulerService.js     ← cron-runner for schedules
        └── socketService.js        ← Socket.IO for live updates to frontend
```

### File-by-file

#### `src/app.js`
- Loads env via `dotenv`
- Connects Mongoose to MongoDB and `pg.Pool` to PostgreSQL
- Mounts all REST routes including the analytics proxy at three paths:
  - `app.use('/api/analytics', analyticsRoutes)`
  - `app.use('/api/ui',        analyticsRoutes)`
  - `app.use('/api/he',        analyticsRoutes)`
- Initializes (in order): Socket.IO, alert engine, registry refresh,
  scheduler, ETL, then MQTT subscriber. The MQTT connection is last so
  early readings can't be dropped before consumers are wired up.
- Listens on `process.env.PORT` (default 3001).

#### `src/config/db.js`
A standard `pg.Pool` configured from `POSTGRES_*` env vars. Reused by every
service that touches PostgreSQL.

#### `src/middleware/authMiddleware.js`
`protect` middleware — verifies the `Authorization: Bearer <jwt>` header
against `JWT_SECRET`, attaches `req.user` and calls `next()`. Returns 401
if missing/invalid. **Mounted on every protected route, including the
analytics proxy.**

#### `src/models/applianceHistory.js`
Mongoose model for the `appliance_history` collection. Fields are AES-GCM
encrypted strings (`*_enc`). Unique index on `(appliance_id, period, aggregation_type)`.

#### `src/models/applianceData.js`
Mongoose model for the `appliance_data` collection. **Plaintext** — what
the analytics service consumes. Schema mirrors what `train.py`/`infer.py`
expect: `device_name`, `node_key`, `interval_start`, `avg/max/min_power_W`,
`total_energy_kWh`, `total_cost_EGP`, `active_minutes`, `idle_minutes`,
`status_changes`. Unique index on `(device_name, interval_start)`.

#### `src/services/mqttService.js`
- Subscribes to topic `home/gateway/data` on `mqtt://mosquitto:1883`
- For each `nodes[nodeKey]` in the payload:
  1. Looks up the appliance via `registry.lookup(gatewayId, nodeKey)`
  2. Computes derived metrics with `metricsService.deriveMetrics(wattage, tariff)`
  3. Calls `influxService.writeEncryptedReading(reading)`
  4. Emits the reading on the internal `eventBus` so other services can react
- Exposes `publishControl({ gatewayId, nodeKey, command, ... })` for the
  appliance toggle endpoint.

#### `src/services/metricsService.js`
Pure-function helper: takes wattage + tariff, returns `{ current, voltage, kwh, cost }`.

#### `src/services/heService.js`
AES-256-GCM helpers (`encryptNumber`, `decryptNumber`). Key derived from
`HE_SECRET` (or `JWT_SECRET` fallback) via SHA-256. Used by InfluxDB writes
and the encrypted ETL output. **Note**: the README calls this "HE" but it
is symmetric encryption, not homomorphic. Real HE lives in
`analytics/src/he_layer.py`.

#### `src/services/influxService.js`
Three exports:
- `writeEncryptedReading(reading)` — encrypts power/current/energy/cost and
  writes one Point to InfluxDB
- `flushWrites()` — explicit flush after each MQTT batch
- `getLiveReadings(applianceId, minutes)` — returns last N min, decrypted,
  for live frontend tiles
- `getAggregatesSince(sinceIso)` — bulk read for ETL, decrypted

#### `src/services/etlService.js`
Cron job (`ETL_CRON`, default `5 * * * *`). Per run:
1. Fetches the last 65 minutes of readings from Influx (decrypts on read).
2. Groups by `(appliance_id, hour-bucket)`, accumulating samples / energy /
   cost / power values / active_count / on_off_cycles.
3. For each group:
   - **Encrypted upsert** into `appliance_history` (existing behaviour)
   - **Plaintext upsert** into `appliance_data` after looking up the
     appliance via `registry.lookupById(g.appliance_id)`. Computes max/min
     from `power_values[]`, `active_minutes` from `(active_count / samples) * 60`,
     and ISO interval start/end from the `period` string.
4. Logs `processed N rows → X history + Y analytics upserts`.

#### `src/services/alertService.js`
Real-time rules engine (separate from ML anomalies):
- **High usage**: `powerW > ALERT_HIGH_USAGE_W`
- **Left on**: continuously `status == 'active'` for `ALERT_LEFT_ON_SECONDS`
- **Offline**: no readings for `ALERT_OFFLINE_SECONDS`

Per-appliance state is kept in-memory; cooldown of `ALERT_COOLDOWN_MS`
between alerts of the same type. Alerts are persisted to PostgreSQL
`alerts` table and emitted on `eventBus` so Socket.IO can push to the UI.

#### `src/services/applianceRegistry.js`
30-second TTL cache of the Postgres `appliances` table joined with
`users.tariff_rate`. Two lookups:
- `lookup(gatewayId, nodeKey)` — used by MQTT ingestion
- `lookupById(applianceId)` — used by ETL

`refresh()` is also called on appliance CRUD to invalidate.

#### `src/services/schedulerService.js`
Reads the `schedules` table and registers each enabled cron with `node-cron`.
On fire, calls `mqttService.publishControl(...)` to send an on/off MQTT
command to the gateway.

#### `src/services/socketService.js`
Socket.IO server bound to the same HTTP server as Express. Subscribes to
`eventBus` events `'reading'` and `'alert'` and pushes them to connected
clients (filtered per user).

#### `src/services/eventBus.js`
A tiny `EventEmitter` shared between services so `mqttService` doesn't
need to know about `alertService` or `socketService`.

#### `src/routes/analyticsRoutes.js` (the proxy)
```
router.use(protect);                        // JWT required
router.all(/.*/, async (req, res) => {
  axios({
    method: req.method,
    url:    `${ANALYTICS_SERVICE_URL}${req.originalUrl}`,
    data:   req.method === 'GET' ? undefined : req.body,
    timeout: 60000,
    validateStatus: () => true,
  })
});
```
- Mounted three times in `app.js`, so `/api/analytics/*`, `/api/ui/*`, and
  `/api/he/*` all flow through it
- 60-second timeout because HE endpoints can take 5–15 s
- Returns 502 if analytics is down, 504 on timeout

---

## 4. Analytics folder reference

```
analytics/
├── Dockerfile
├── requirements.txt
├── .env / .env.example
├── app.py                            ← entry point (boots Flask + scheduler)
└── src/
    ├── shared.py                     ← single-source-of-truth: Mongo + severity + ML config
    ├── api.py                        ← Flask app + core analytics endpoints
    ├── api_ui_endpoints.py           ← UI-shaped chart endpoints (Blueprint)
    ├── he_layer.py                   ← Homomorphic encryption demo (Blueprint)
    ├── model_manager.py              ← per-device adaptive lifecycle (LEARNING → READY)
    ├── classifier.py                 ← rule layer that labels each anomaly type
    ├── forecaster.py                 ← per-device energy forecaster (Linear Regression)
    ├── infer.py                      ← adaptive inference tick + run_inference()
    ├── scripts/                      ← manual dev / ops utilities
    │   ├── train.py                  ← force-train devices past the readiness gate
    │   ├── evaluate.py               ← confusion matrix vs ground truth
    │   ├── reset_db.py               ← clear alerts + checkpoints + device models
    │   ├── seed_synthetic.py         ← generate hourly test data (Kitchen/Laundry/Climate)
    │   ├── classify_backfill.py      ← re-label pre-existing alerts (idempotent)
    │   └── analytics2.py             ← print-style aggregation dump
    └── tests/
        └── test_e2e.py               ← end-to-end assertions
```

> Trained models are **not** files: each device's Isolation Forest + scaler +
> baseline live in the Mongo `device_models` collection, created at runtime and
> surviving container rebuilds (there is no `models/` directory).

### File-by-file

#### `app.py`
The only file Docker runs (`CMD ["python", "-u", "app.py"]`).
- Adds `src/` to `sys.path` so the modules inside are importable as top-level modules
- `from api import app` — this triggers `api.py` which builds the Flask app
  and registers the UI + HE blueprints
- Starts an APScheduler `BackgroundScheduler` that calls
  `infer.run_inference()` every `INFER_INTERVAL_MIN` minutes (default 30)
- `app.run(host='0.0.0.0', port=FLASK_PORT)` — binds to all interfaces
  inside the container so Docker can route external traffic in

#### `src/shared.py`
Created during the integration. Holds:
- `client`, `db`, `data_col`, `alerts_col`, `checkpoint_col` — env-driven
  Mongo connection (`MONGO_URI`, `MONGO_DB`)
- `SEVERITY_THRESHOLDS`, `SEVERITY_COLORS`, `DEVICE_COLORS`,
  `score_to_severity()` — used by both `api.py` and `api_ui_endpoints.py`
- `INTERVAL_MINUTES` (60 = backend hourly, 30 = synthetic seed) — used by
  feature engineering
- `MODELS_DIR`, `FEATURES` — single source of truth for ML configuration

#### `src/api.py`
- Imports `shared` for DB + severity, imports `ui_bp` from
  `api_ui_endpoints`, defensively imports `he_bp` from `he_layer`
- Creates `app = Flask(__name__)`, registers blueprints, enables CORS
- Adds `before_request` / `after_request` for structured request logging
- Defines validation helpers (`validate_date`, `validate_int`,
  `validate_appliance_id`)
- Defines all `/api/health` and `/api/analytics/*` route handlers

#### `src/api_ui_endpoints.py`
Flask Blueprint `ui_bp`. Exposes endpoints pre-shaped for Chart.js /
ApexCharts (no transformation needed on the frontend):
- `/api/ui/dashboard` — KPI cards, donut, line chart, peak-hours bars,
  anomaly summary, recent alerts — all in one round-trip
- `/api/ui/charts/energy-trend` — multi-line chart (one line per device)
- `/api/ui/charts/cost-breakdown` — horizontal bar with shares
- `/api/ui/anomalies/feed` — paginated alerts with severity badges
- `/api/ui/anomalies/heatmap` — device × day matrix

#### `src/he_layer.py`
Flask Blueprint `he_bp`. Demonstrates homomorphic encryption (CKKS via
TenSEAL):
- `build_he_context()` — generates a CKKS keypair with poly_modulus_degree
  8192 (128-bit security)
- `get_he_context()` — module-level cache so we don't regenerate keys per
  request
- `he_sum_vector`, `he_mean_vector`, `he_weighted_cost_share` — the actual
  encrypted ops
- `run_he_analytics()` — full pipeline + plaintext verification
- Exposes `/api/he/summary` and `/api/he/verify`
- **Falls back gracefully**: if TenSEAL is missing, `api.py`'s try/except
  skips registering this blueprint — the rest of the API still serves.

#### `src/scripts/train.py`
CLI script. Reads all docs from `appliance_data`, engineers features (no
rolling windows — `runtime_ratio = active_minutes / INTERVAL_MINUTES`,
`power_x_runtime = avg_power_W * runtime_ratio`), fits one Isolation
Forest + StandardScaler per device, dumps everything to `models/`.

Tunables via env: `CONTAMINATION` (default 0.003).

#### `src/infer.py`
Two entry points:
- **CLI** (`python infer.py`) — runs once and prints recent alerts
- **`run_inference()` function** — called every 30 min by the scheduler in
  `app.py`

Logic: load checkpoint → query records since checkpoint → for each device
load its model + scaler → predict → write detected anomalies to
`anomaly_alerts` → save new checkpoint with `last_interval_start`.

#### `src/scripts/evaluate.py`
CLI. For datasets that have ground-truth labels (synthetic), prints
confusion matrix, per-device precision/recall, ROC-AUC, missed-anomaly
listing, recall by anomaly type.

#### `src/scripts/reset_db.py`
CLI. Drops `anomaly_alerts` and `infer_checkpoint`. **Never touches**
`appliance_data` (that's owned by the backend ETL).

#### `src/scripts/seed_synthetic.py`
CLI. Generates 60 days × 5 devices × 48 30-min intervals = 14,400 docs
into `appliance_data`, with 40 injected anomalies of 4 types (power_spike,
excessive_runtime, abnormal_idle, stuck_on). Used for development before
real backend data exists.

#### `src/scripts/analytics2.py`
Standalone print-style dump of daily / weekly / monthly / peak-hours /
per-appliance totals / anomaly counts. Useful for quick CLI inspection.

#### `src/tests/test_e2e.py`
50+ assertions across 7 layers: MongoDB connectivity, schema integrity,
feature engineering math, model files, API endpoints, UI endpoints, HE
layer, cross-layer consistency (Mongo totals must match API totals).

---

## 5. End-to-end data pipeline

### Ingestion (real-time)

```
[Smart plug / Simulator]
        │ MQTT publish home/gateway/data {nodes: {...}}
        ▼
[Mosquitto broker]
        │
        ▼
[Backend mqttService] ──────── eventBus ──── [alertService] ── Postgres alerts
        │                              └──── [socketService] ── frontend live
        │
        ▼ writeEncryptedReading
[InfluxDB] (encrypted readings)
```

Per reading: lookup appliance in registry → derive current/voltage/kWh/cost →
encrypt with AES-GCM → write Point to Influx.

### Aggregation (every hour)

```
[etlService cron tick]
        │
        │ getAggregatesSince(now - 65 min)   ← decrypts on read
        ▼
[Group by (appliance_id, hour) in Node memory]
        │
        ├── encryptNumber(...) → ApplianceHistory.updateOne({upsert:true})
        │       → MongoDB.appliance_history (encrypted)
        │
        └── registry.lookupById(appliance_id)
            ApplianceData.updateOne({upsert:true})
                → MongoDB.appliance_data (plaintext)
```

### ML inference (every 30 min, inside analytics container)

```
[APScheduler tick → infer.run_inference()]
        │
        │ checkpoint_col.find_one(sort=scored_at desc)
        ▼
[query data_col where interval_start > last_scored]
        │
        │ engineer_features (runtime_ratio, power_x_runtime)
        ▼
[for each device → load .pkl → predict + decision_function]
        │
        ├── insert anomalies into anomaly_alerts
        └── insert new checkpoint with latest interval_start
```

### Read path (dashboard view)

```
[Browser] GET http://localhost:3001/api/ui/dashboard
        │ Authorization: Bearer <jwt>
        ▼
[Backend Express]
  protect middleware → validate JWT → 401 if invalid
        │
        ▼
[analyticsRoutes proxy]
  axios.get(`${ANALYTICS_SERVICE_URL}${req.originalUrl}`)
        │
        ▼
[Analytics Flask  http://analytics:5000/api/ui/dashboard]
        │
        ▼
[ui_dashboard handler]
  6 MongoDB aggregations on appliance_data + anomaly_alerts
        │
        ▼
[JSON response] ──── back up the chain ────► browser
```

---

## 6. Endpoint reference

### Backend-native (port 3001)

All require `Authorization: Bearer <jwt>` unless noted.

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/` | Liveness probe | none |
| GET | `/health` | Uptime + status | none |
| POST | `/api/auth/signup` | Create user | none |
| POST | `/api/auth/login` | Get JWT | none |
| GET | `/api/users/me` | Profile | yes |
| PUT | `/api/users/me/tariff` | Update tariff rate | yes |
| GET | `/api/appliances` | List user's appliances | yes |
| POST | `/api/appliances` | Register new appliance | yes |
| PUT | `/api/appliances/:id/toggle` | Send on/off MQTT command | yes |
| DELETE | `/api/appliances/:id` | Remove appliance | yes |
| GET | `/api/schedules` | List schedules | yes |
| POST | `/api/schedules` | Create schedule | yes |
| PUT | `/api/schedules/:id` | Update | yes |
| DELETE | `/api/schedules/:id` | Delete | yes |
| GET | `/api/alerts` | List rule-based alerts | yes |
| PUT | `/api/alerts/:id/read` | Mark read | yes |

### Backend → Analytics proxy (port 3001)

All require JWT. Same path on analytics container.

#### Core analytics

| Method | Path | Query params | Returns |
|---|---|---|---|
| GET | `/api/health` | — | DB status, record count, alert count |
| GET | `/api/analytics/summary` | — | Grand totals + per-device + projected bill + peak hours + anomaly summary |
| GET | `/api/analytics/:applianceId/daily` | `from`, `to`, `page`, `page_size` | Per-day energy/cost/power |
| GET | `/api/analytics/:applianceId/weekly` | `from`, `to` | ISO week aggregates |
| GET | `/api/analytics/:applianceId/monthly` | — | Per-month aggregates with month_name |
| GET | `/api/analytics/:applianceId/peak-hours` | `limit` (1–24) | Top N hours by energy |
| GET | `/api/analytics/total/cost` | — | Grand total + per-device with share_of_total_pct |
| GET | `/api/analytics/anomalies` | `device`, `severity`, `sort`, `limit`, `offset`, `from`, `to` | Paginated alerts + severity counts + by-device summary |
| GET | `/api/analytics/bill-estimate` | `days` (1–365) | Projected bill from average daily cost |

`:applianceId` accepts:
- `all` — every device
- A `node_key` (e.g. `node_1`) — exact match
- A `device_name` (e.g. `Microwave`) — case-insensitive

#### UI-shaped (chart-ready)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/ui/dashboard` | KPI cards + cost donut + energy trend + peak hours + anomaly summary + recent 5 alerts |
| GET | `/api/ui/charts/energy-trend` | Multi-line chart, `?granularity=daily\|weekly\|monthly` |
| GET | `/api/ui/charts/cost-breakdown` | Horizontal bar + table data |
| GET | `/api/ui/anomalies/feed` | Severity-filtered feed with badges + bg colours |
| GET | `/api/ui/anomalies/heatmap` | Device × day matrix + ApexCharts series |

#### Homomorphic encryption (optional, slow ~5–15s)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/he/summary` | Encrypted aggregations per device + plaintext reference + approximation errors |
| GET | `/api/he/verify` | Side-by-side comparison with within-tolerance verdict |

---

## 7. Connection diagram

```
                           ┌──────────────┐
                           │   Browser    │ (Next.js)
                           └──────┬───────┘
                                  │ JWT-authenticated HTTP
                                  │ http://localhost:3001/...
                                  ▼
   ┌───────────────────────────────────────────────────────────────┐
   │                    Backend (Express, :3001)                    │
   │ ┌──────────────────────────────────────────────────────────┐  │
   │ │ middleware/authMiddleware.protect   (JWT validation)     │  │
   │ ├──────────────────────────────────────────────────────────┤  │
   │ │ /api/auth/* /api/users/* /api/appliances/* /api/alerts/* │  │
   │ │ /api/schedules/*                                         │  │
   │ ├──────────────────────────────────────────────────────────┤  │
   │ │ /api/analytics/*  /api/ui/*  /api/he/*                   │  │
   │ │   ↳ analyticsRoutes.js (axios proxy)                     │  │
   │ └────────────┬─────────────────────────────────────────────┘  │
   └──────────────┼────────────────────────────────────────────────┘
                  │  axios → http://analytics:5000/<originalUrl>
                  ▼
   ┌───────────────────────────────────────────────────────────────┐
   │                  Analytics (Flask, :5000)                      │
   │ ┌──────────────────────────────────────────────────────────┐  │
   │ │ app.py  (entry point + APScheduler)                      │  │
   │ │   └─ from api import app                                 │  │
   │ │       ├─ ui_bp     (api_ui_endpoints.py)                 │  │
   │ │       └─ he_bp     (he_layer.py — optional)              │  │
   │ └──────────────────────────────────────────────────────────┘  │
   └────┬─────────────────────────────┬────────────────────────────┘
        │                             │
        │ pymongo                     │ APScheduler tick
        ▼                             ▼
   ┌──────────────┐            ┌─────────────────────────┐
   │  MongoDB     │ ◄────────  │ infer.run_inference()   │
   │ (:27017)     │            │ • read appliance_data    │
   │              │            │ • predict per-device     │
   │ collections: │            │ • write anomaly_alerts   │
   │ • appliance_data           • update infer_checkpoint │
   │ • appliance_history        └─────────────────────────┘
   │ • anomaly_alerts
   │ • infer_checkpoint │
   └──────────▲───────┘
              │  ETL upserts (every hour)
              │
   ┌──────────┴────────────┐
   │ Backend etlService    │
   │ • read InfluxDB       │
   │ • encrypted →         │
   │   appliance_history   │
   │ • plaintext →         │
   │   appliance_data      │
   └──────────▲────────────┘
              │ getAggregatesSince
              │
   ┌──────────┴────────┐         ┌──────────────────┐
   │  InfluxDB :8086   │ ◄──── writeEncryptedReading │
   │  (encrypted       │         │                  │
   │   per-second      │         │ Backend          │
   │   readings)       │         │ mqttService      │
   └───────────────────┘         └────────▲─────────┘
                                          │ MQTT subscribe
                                          │ home/gateway/data
                                ┌─────────┴─────────┐
                                │ Mosquitto :1883   │
                                └─────────▲─────────┘
                                          │ MQTT publish
                                ┌─────────┴─────────┐
                                │ Smart plug /      │
                                │ Simulator         │
                                └───────────────────┘
```

---

## 8. Scenarios — what happens when…

### 8.1 A new reading arrives from a smart plug

1. Plug publishes JSON `{ gateway_id, nodes: { node_1: { wattage: 110, status: "active" } } }` to `home/gateway/data`.
2. `mqttService` parses, iterates nodes, calls `registry.lookup(gatewayId, "node_1")` → finds the appliance UUID + tariff.
3. `metricsService.deriveMetrics(110, tariff)` → `{ current, voltage, kwh, cost }`.
4. `influxService.writeEncryptedReading(...)` encrypts power/current/energy/cost and writes to Influx.
5. The reading is also emitted on `eventBus`. `alertService` may fire a `high_usage` / `left_on` rule alert. `socketService` pushes the live reading to the user's open dashboard.

### 8.2 The hourly ETL fires

1. Cron `5 * * * *` triggers `etlService.runOnce()`.
2. Reads last 65 min from Influx (decrypted on read).
3. Groups by `(appliance_id, hour)`. For one hour-bucket of `Main Refrigerator`:
   - 3600 readings → samples=3600, energy_sum=0.108 kWh, active_count=2841
4. Two writes:
   - Encrypted: `appliance_history` upsert with `total_energy_kWh_enc`, `avg_power_W_enc`, `total_cost_enc`, `peak_hour`, `ml_features`.
   - Plaintext: `appliance_data` upsert with `device_name`, `interval_start`, `avg/max/min_power_W`, `total_energy_kWh`, `total_cost_EGP`, `active_minutes` (`(2841/3600)*60 = 47`), `idle_minutes` (`13`), `status_changes` (`on_off_cycles`).

### 8.3 A user opens the dashboard page

1. Browser loads Next.js page; React calls `fetch('/api/ui/dashboard', { headers: { Authorization: ... } })`.
2. Backend `protect` middleware validates JWT.
3. `analyticsRoutes` catch-all calls `axios.get('http://analytics:5000/api/ui/dashboard')`.
4. Analytics `ui_dashboard` handler runs 6 aggregations on `appliance_data` and 1 on `anomaly_alerts`.
5. Returns `{ kpi_cards, cost_donut, energy_trend, peak_hours, anomaly_summary, recent_alerts }`.
6. Backend forwards JSON to browser. Chart.js consumes `energy_trend` directly with no transformation.

### 8.4 The 30-min inference scheduler ticks

1. APScheduler in `analytics/app.py` calls `infer.run_inference()`.
2. Loads `infer_checkpoint` → finds last scored `interval_start = "2026-04-28T13:00:00Z"`.
3. Queries `appliance_data` for docs with `interval_start > "2026-04-28T13:00:00Z"`.
4. For each device, loads its `.pkl` + scaler, predicts on engineered features.
5. Writes any flagged rows to `anomaly_alerts` (with severity, score, full reading context).
6. Writes a new `infer_checkpoint` with `last_interval_start = "2026-04-28T14:00:00Z"`.
7. APScheduler logs `Inference tick: {records_scored: 5, alerts_raised: 1}`.

### 8.5 Operator confirms an alert is real (future loop)

Not yet implemented, but the schema supports it:
1. Frontend POSTs `{ alert_id, confirmed: true, label: "stuck_on" }` to a future endpoint.
2. Backend updates the corresponding `appliance_data` doc with `anomaly: "stuck_on"`.
3. Next time `train.py` runs, `evaluate.py` can use it as ground-truth for retraining.

### 8.6 A new appliance is added to a household

1. User POSTs `/api/appliances` with `name, node_key, gateway_id`.
2. Postgres insert; `registry.invalidate()` so the cache reloads on next reading.
3. Smart plug starts publishing → readings flow through MQTT → ETL aggregates.
4. **For ~2–4 weeks**: `appliance_data` accumulates rows for this device, but
   `infer.run_inference()` skips it (no `.pkl` model exists yet — silent skip
   with a warning log).
5. After enough data, you run `docker compose exec analytics python src/scripts/train.py`. A new model is fitted on this device's data and saved as `<DeviceName>_model.pkl`.
6. From the next inference tick onwards, this device gets anomaly detection.

### 8.7 The TenSEAL install fails on a particular host

1. `pip install tenseal` fails during `docker build` (no wheel for the arch, build tools insufficient).
2. **The build still succeeds** because the Dockerfile installs `build-essential cmake` as a fallback compilation path.
3. If even that fails, the container still starts: `api.py` catches `ImportError` from `from he_layer import he_bp` and logs a warning. All non-HE endpoints continue to work; `/api/he/*` returns 404.

### 8.8 Analytics container is down when the frontend asks for the dashboard

1. Browser calls `/api/ui/dashboard` on the backend.
2. Backend's axios proxy gets `ECONNREFUSED`.
3. Returns `502 { status: "error", message: "Analytics service unavailable" }`.
4. Frontend can show a "Dashboard temporarily unavailable" state instead of crashing.

---

## 9. Operations & runbook

### Bring everything up

```bash
docker compose up --build
```

First boot of the analytics container is slow (~3–5 min) because TenSEAL
needs to compile if no wheel is available.

### Logs

```bash
docker compose logs -f backend
docker compose logs -f analytics
```

Look for `🗄  ETL: processed N rows → X history + Y analytics upserts`
on the backend, and `Inference tick: {records_scored: ..., alerts_raised: ...}`
on the analytics.

### Train models

```bash
docker compose exec analytics python src/scripts/train.py
```

After ~2–4 weeks of real data accumulating in `appliance_data`. Tweak
contamination via env: `CONTAMINATION=0.005 docker compose exec ...`.

### Wipe ML state and re-score from scratch

```bash
docker compose exec analytics python src/scripts/reset_db.py
# then wait for the scheduler tick, or trigger manually:
docker compose exec analytics python src/infer.py
```

### Seed synthetic data (for dev)

```bash
docker compose exec analytics python src/scripts/seed_synthetic.py
```

### Run end-to-end test suite

```bash
docker compose exec analytics python src/tests/test_e2e.py
```

### Test the analytics directly (bypasses backend auth)

```bash
curl http://localhost:5000/api/health
curl http://localhost:5000/api/ui/dashboard
```

### Test through the backend proxy (requires JWT)

```bash
TOKEN=$(curl -s -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"...","password":"..."}' | jq -r .token)

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:3001/api/ui/dashboard
```

### Environment variables that matter

#### Backend (`backend/.env`)
| Var | Purpose | Default |
|---|---|---|
| `PORT` | HTTP port | 3001 |
| `JWT_SECRET` | Sign/verify JWTs | required |
| `MONGO_URI` | Mongoose connection | `mongodb://mongodb:27017/shemms` |
| `INFLUXDB_URL` `INFLUXDB_TOKEN` `INFLUXDB_ORG` `INFLUXDB_BUCKET` | InfluxDB | required |
| `MQTT_BROKER_URL` | Broker | `mqtt://mosquitto:1883` |
| `ANALYTICS_SERVICE_URL` | Proxy target | `http://analytics:5000` |
| `ANALYTICS_TIMEOUT_MS` | Proxy timeout | 60000 |
| `HE_SECRET` | AES-GCM key derivation | required |
| `ETL_CRON` | Cron expression | `5 * * * *` |
| `ETL_LOOKBACK_MIN` | Window pulled from Influx per ETL tick | 65 |
| `ALERT_HIGH_USAGE_W` `ALERT_LEFT_ON_SECONDS` `ALERT_OFFLINE_SECONDS` `ALERT_COOLDOWN_MS` | Real-time alert tuning | see code |

#### Analytics (`analytics/.env`)
| Var | Purpose | Default |
|---|---|---|
| `MONGO_URI` | PyMongo connection | `mongodb://mongodb:27017/shemms` |
| `MONGO_DB` | Database name | `shemms` |
| `FLASK_PORT` | HTTP port | 5000 |
| `INFER_ENABLED` | Toggle background scheduler | `true` |
| `INFER_INTERVAL_MIN` | Scheduler period | 30 |
| `INTERVAL_MINUTES` | Aggregation window length (60 = backend hourly) | 60 |
| `CONTAMINATION` | Isolation Forest expected anomaly rate | 0.003 |
| `MODELS_DIR` | Where `.pkl` files live | `analytics/models/` |

---

*Last updated as part of the analytics ↔ backend integration milestone.*
