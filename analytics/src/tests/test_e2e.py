"""
test_e2e.py
-----------
Full end-to-end test suite for the Smart Home Energy Monitoring System.
Tests every layer: MongoDB → ML models → API endpoints → UI endpoints → HE layer.

Run against a running analytics service (e.g. the Docker container):
  pip install requests
  python src/tests/test_e2e.py
  # override the target with ANALYTICS_API_BASE / MONGO_URI env vars

What gets tested:
  ✅ Layer 1 — MongoDB connectivity and data integrity
  ✅ Layer 2 — Feature engineering correctness
  ✅ Layer 3 — ML model files and prediction consistency
  ✅ Layer 4 — Core API endpoints (health, summary, analytics, anomalies)
  ✅ Layer 5 — UI-ready endpoints (dashboard, charts, feed, heatmap)
  ✅ Layer 6 — HE layer (if tenseal installed)
  ✅ Layer 7 — Cross-layer consistency (API totals match MongoDB aggregation)

Output: colour-coded pass/fail per test + final summary report
"""

import sys
import os
import time

try:
    import requests
except ImportError:
    print("❌  'requests' not installed. Run: pip install requests")
    sys.exit(1)

try:
    import pymongo
except ImportError:
    print("❌  'pymongo' not installed. Run: pip install pymongo")
    sys.exit(1)

try:
    import pandas as pd
    import numpy as np
    import joblib
    from sklearn.ensemble import IsolationForest
except ImportError:
    print("❌  ML dependencies missing. Run: pip install pandas numpy scikit-learn joblib")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

MONGO_URI  = os.environ.get("MONGO_URI", "mongodb://localhost:27017/shemms")
DB_NAME    = os.environ.get("MONGO_DB",  "shemms")

API_BASE   = os.environ.get("ANALYTICS_API_BASE", "http://127.0.0.1:5000")
HE_TIMEOUT = 60
MODELS_DIR = os.environ.get(
    "MODELS_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))
)

EXPECTED_DEVICES = [
    "Beverage Fridge", "Deep Freezer",
    "Main Refrigerator", "Microwave", "Water Dispenser"
]
EXPECTED_FEATURES = [
    "avg_power_W", "max_power_W", "total_energy_kWh",
    "active_minutes", "idle_minutes", "runtime_ratio", "power_x_runtime",
]
EXPECTED_MIN_RECORDS   = 14000
EXPECTED_MIN_ANOMALIES = 30
TOLERANCE_PCT          = 1.0   # cross-layer value tolerance in percent

# ── Colour helpers ────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def green(s):  return f"{GREEN}{s}{RESET}"
def red(s):    return f"{RED}{s}{RESET}"
def yellow(s): return f"{YELLOW}{s}{RESET}"
def cyan(s):   return f"{CYAN}{s}{RESET}"
def bold(s):   return f"{BOLD}{s}{RESET}"

# ── Test runner state ─────────────────────────────────────────────────────────

results = []   # list of (layer, test_name, passed, message)

def run_test(layer: str, name: str, fn):
    """Runs a single test function, records pass/fail, prints result."""
    try:
        t0  = time.perf_counter()
        msg = fn()
        ms  = (time.perf_counter() - t0) * 1000
        results.append((layer, name, True, msg or ""))
        print(f"  {green('✅')} {name:<55} {green('PASS')}  ({ms:.0f}ms)"
              + (f"  {msg}" if msg else ""))
    except AssertionError as e:
        results.append((layer, name, False, str(e)))
        print(f"  {red('❌')} {name:<55} {red('FAIL')}  {e}")
    except Exception as e:
        results.append((layer, name, False, f"ERROR: {e}"))
        print(f"  {red('❌')} {name:<55} {red('ERROR')} {e}")

def section(title: str):
    print(f"\n{bold(cyan('━' * 65))}")
    print(f"{bold(cyan(f'  {title}'))}")
    print(f"{bold(cyan('━' * 65))}")

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — MongoDB
# ═══════════════════════════════════════════════════════════════════════════════

def test_mongo_connect():
    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return "ping OK"

def test_mongo_collections_exist():
    client = pymongo.MongoClient(MONGO_URI)
    db     = client[DB_NAME]
    cols   = db.list_collection_names()
    assert "appliance_data"  in cols, f"Missing collection: appliance_data (found: {cols})"
    assert "anomaly_alerts"  in cols, f"Missing collection: anomaly_alerts (found: {cols})"
    return f"collections: {cols}"

def test_mongo_record_count():
    client = pymongo.MongoClient(MONGO_URI)
    count  = client[DB_NAME]["appliance_data"].count_documents({})
    assert count >= EXPECTED_MIN_RECORDS, \
        f"Only {count} records — expected ≥ {EXPECTED_MIN_RECORDS}"
    return f"{count} records"

def test_mongo_devices_present():
    client  = pymongo.MongoClient(MONGO_URI)
    devices = client[DB_NAME]["appliance_data"].distinct("device_name")
    missing = [d for d in EXPECTED_DEVICES if d not in devices]
    assert not missing, f"Missing devices: {missing}"
    return f"{len(devices)} devices"

def test_mongo_schema_fields():
    client = pymongo.MongoClient(MONGO_URI)
    sample = client[DB_NAME]["appliance_data"].find_one({}, {"_id": 0})
    required = ["device_name", "interval_start", "avg_power_W", "max_power_W",
                "total_energy_kWh", "active_minutes", "idle_minutes", "total_cost_EGP"]
    missing = [f for f in required if f not in sample]
    assert not missing, f"Missing schema fields: {missing}"
    return f"{len(sample)} fields per record"

def test_mongo_no_null_power():
    client = pymongo.MongoClient(MONGO_URI)
    nulls  = client[DB_NAME]["appliance_data"].count_documents(
        {"avg_power_W": {"$exists": False}}
    )
    assert nulls == 0, f"{nulls} records missing avg_power_W"
    return "no null power fields"

def test_mongo_anomaly_labels():
    client = pymongo.MongoClient(MONGO_URI)
    count  = client[DB_NAME]["appliance_data"].count_documents(
        {"anomaly": {"$ne": None, "$exists": True}}
    )
    assert count >= EXPECTED_MIN_ANOMALIES, \
        f"Only {count} labeled anomalies — expected ≥ {EXPECTED_MIN_ANOMALIES}"
    return f"{count} labeled anomalies"

def test_mongo_alerts_written():
    client = pymongo.MongoClient(MONGO_URI)
    count  = client[DB_NAME]["anomaly_alerts"].count_documents({})
    assert count > 0, "anomaly_alerts collection is empty — run infer.py first"
    return f"{count} alerts stored"

def test_mongo_alert_schema():
    client = pymongo.MongoClient(MONGO_URI)
    alert  = client[DB_NAME]["anomaly_alerts"].find_one({}, {"_id": 0})
    assert alert, "No alerts found"
    required = ["device_name", "interval_start", "avg_power_W",
                "anomaly_score", "scored_at"]
    missing  = [f for f in required if f not in alert]
    assert not missing, f"Alert missing fields: {missing}"
    return f"{len(alert)} fields per alert"

def test_mongo_checkpoint_written():
    client = pymongo.MongoClient(MONGO_URI)
    chk    = client[DB_NAME]["infer_checkpoint"].find_one()
    assert chk, "No checkpoint found — run infer.py first"
    assert "last_interval_start" in chk, "Checkpoint missing last_interval_start"
    return f"last scored: {chk['last_interval_start']}"

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — Feature engineering
# ═══════════════════════════════════════════════════════════════════════════════

def engineer_features(df):
    df = df.copy()
    df["runtime_ratio"]   = df["active_minutes"] / 30.0
    df["power_x_runtime"] = df["avg_power_W"] * df["runtime_ratio"]
    return df

def test_feature_runtime_ratio():
    df  = pd.DataFrame([{"active_minutes": 15, "avg_power_W": 100.0,
                          "max_power_W": 150.0, "total_energy_kWh": 0.05,
                          "idle_minutes": 15}])
    out = engineer_features(df)
    assert abs(out["runtime_ratio"].iloc[0] - 0.5) < 1e-9, \
        f"runtime_ratio wrong: {out['runtime_ratio'].iloc[0]}"
    return "runtime_ratio = 0.5 ✓"

def test_feature_power_x_runtime():
    df  = pd.DataFrame([{"active_minutes": 30, "avg_power_W": 200.0,
                          "max_power_W": 250.0, "total_energy_kWh": 0.1,
                          "idle_minutes": 0}])
    out = engineer_features(df)
    expected = 200.0 * 1.0
    assert abs(out["power_x_runtime"].iloc[0] - expected) < 1e-9, \
        f"power_x_runtime wrong: {out['power_x_runtime'].iloc[0]} != {expected}"
    return f"power_x_runtime = {expected} ✓"

def test_feature_zero_active():
    df  = pd.DataFrame([{"active_minutes": 0, "avg_power_W": 0.0,
                          "max_power_W": 0.0, "total_energy_kWh": 0.0,
                          "idle_minutes": 30}])
    out = engineer_features(df)
    assert out["runtime_ratio"].iloc[0]   == 0.0, "runtime_ratio should be 0 for idle"
    assert out["power_x_runtime"].iloc[0] == 0.0, "power_x_runtime should be 0 for idle"
    return "zero active handled correctly ✓"

def test_feature_no_nan():
    client  = pymongo.MongoClient(MONGO_URI)
    records = list(client[DB_NAME]["appliance_data"].find({}, {"_id": 0}).limit(500))
    df      = engineer_features(pd.DataFrame(records))
    nan_cols = df[EXPECTED_FEATURES].isnull().sum()
    bad      = nan_cols[nan_cols > 0]
    assert bad.empty, f"NaN values in features after fillna(0): {bad.to_dict()}"
    return "no NaN in features ✓"

def test_feature_values_in_range():
    client  = pymongo.MongoClient(MONGO_URI)
    records = list(client[DB_NAME]["appliance_data"].find({}, {"_id": 0}).limit(500))
    df      = engineer_features(pd.DataFrame(records))
    assert (df["runtime_ratio"] >= 0).all() and (df["runtime_ratio"] <= 1.01).all(), \
        "runtime_ratio out of [0,1] range"
    assert (df["avg_power_W"] >= 0).all(), "negative avg_power_W found"
    return "all feature values in expected ranges ✓"

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — ML models
# ═══════════════════════════════════════════════════════════════════════════════

def test_model_files_exist():
    missing = []
    for device in EXPECTED_DEVICES:
        slug = device.replace(" ", "_")
        for suffix in ("_model.pkl", "_scaler.pkl"):
            path = os.path.join(MODELS_DIR, slug + suffix)
            if not os.path.exists(path):
                missing.append(path)
    assert not missing, f"Missing model files: {missing}"
    return f"{len(EXPECTED_DEVICES) * 2} model files found ✓"

def test_model_metadata():
    path = os.path.join(MODELS_DIR, "training_metadata.pkl")
    assert os.path.exists(path), f"Missing: {path}"
    meta = joblib.load(path)
    assert "features"        in meta, "metadata missing 'features'"
    assert "devices_trained" in meta, "metadata missing 'devices_trained'"
    assert "trained_at"      in meta, "metadata missing 'trained_at'"
    assert meta["features"]  == EXPECTED_FEATURES, \
        f"Feature mismatch: {meta['features']} != {EXPECTED_FEATURES}"
    return f"trained at {meta['trained_at'][:19]}"

def test_model_feature_sync():
    meta = joblib.load(os.path.join(MODELS_DIR, "training_metadata.pkl"))
    assert set(meta["features"]) == set(EXPECTED_FEATURES), \
        f"train.py features != expected: {set(meta['features']) ^ set(EXPECTED_FEATURES)}"
    return "train/infer/evaluate features in sync ✓"

def test_model_predict_smoke():
    device     = EXPECTED_DEVICES[0]
    slug       = device.replace(" ", "_")
    model      = joblib.load(os.path.join(MODELS_DIR, f"{slug}_model.pkl"))
    scaler     = joblib.load(os.path.join(MODELS_DIR, f"{slug}_scaler.pkl"))
    dummy_row  = pd.DataFrame([{f: 0.5 for f in EXPECTED_FEATURES}])
    X_scaled   = scaler.transform(dummy_row)
    pred       = model.predict(X_scaled)
    score      = model.decision_function(X_scaled)
    assert pred[0]  in (-1, 1),           f"Unexpected prediction value: {pred[0]}"
    assert isinstance(score[0], float),   f"Score not float: {score[0]}"
    return f"prediction={pred[0]}, score={score[0]:.4f} ✓"

def test_model_scaler_dimensions():
    for device in EXPECTED_DEVICES:
        slug   = device.replace(" ", "_")
        scaler = joblib.load(os.path.join(MODELS_DIR, f"{slug}_scaler.pkl"))
        assert scaler.n_features_in_ == len(EXPECTED_FEATURES), \
            f"{device}: scaler has {scaler.n_features_in_} features, expected {len(EXPECTED_FEATURES)}"
    return f"all scalers have {len(EXPECTED_FEATURES)} features ✓"

def test_model_contamination_rate():
    client  = pymongo.MongoClient(MONGO_URI)
    records = list(client[DB_NAME]["appliance_data"].find(
        {"device_name": EXPECTED_DEVICES[0]}, {"_id": 0}
    ))
    df     = engineer_features(pd.DataFrame(records))
    slug   = EXPECTED_DEVICES[0].replace(" ", "_")
    model  = joblib.load(os.path.join(MODELS_DIR, f"{slug}_model.pkl"))
    scaler = joblib.load(os.path.join(MODELS_DIR, f"{slug}_scaler.pkl"))
    X      = df[EXPECTED_FEATURES].fillna(0)
    preds  = model.predict(scaler.transform(X))
    rate   = (preds == -1).sum() / len(preds)
    assert rate < 0.05, f"Anomaly rate too high: {rate:.1%} — check contamination"
    return f"anomaly rate = {rate:.2%} (within acceptable range) ✓"

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — Core API endpoints
# ═══════════════════════════════════════════════════════════════════════════════

def get(path, params=None):
    r = requests.get(f"{API_BASE}{path}", params=params, timeout=15)
    assert r.status_code == 200, f"HTTP {r.status_code} on {path}: {r.text[:200]}"
    body = r.json()
    assert body.get("status") == "ok", f"status != ok: {body}"
    return body["data"]

def test_api_health():
    data = get("/api/health")
    assert data["database"] == "connected", "database not connected"
    assert data["records"]  >  0,           "no records reported"
    return f"{data['records']} records, {data['alerts']} alerts"

def test_api_summary():
    data = get("/api/analytics/summary")
    assert "totals"      in data, "missing 'totals'"
    assert "per_device"  in data, "missing 'per_device'"
    assert "anomalies"   in data, "missing 'anomalies'"
    assert "peak_hours"  in data, "missing 'peak_hours'"
    assert data["totals"]["energy_kWh"] > 0, "zero total energy"
    assert data["totals"]["cost_EGP"]   > 0, "zero total cost"
    return f"energy={data['totals']['energy_kWh']}kWh, cost={data['totals']['cost_EGP']}EGP"

def test_api_daily():
    data = get("/api/analytics/Microwave/daily")
    assert "records"    in data,           "missing 'records'"
    assert "pagination" in data,           "missing pagination"
    assert len(data["records"]) > 0,       "no daily records returned"
    assert "date"       in data["records"][0], "record missing 'date'"
    return f"{data['pagination']['total_records']} daily records"

def test_api_daily_pagination():
    data = get("/api/analytics/Microwave/daily", {"page": 1, "page_size": 5})
    assert len(data["records"]) <= 5,            "page_size not respected"
    assert data["pagination"]["page"]      == 1, "wrong page number"
    assert data["pagination"]["page_size"] == 5, "wrong page_size"
    return "pagination works ✓"

def test_api_daily_date_filter():
    data = get("/api/analytics/Microwave/daily",
               {"from": "2026-01-01", "to": "2026-01-31"})
    dates = [r["date"] for r in data["records"]]
    assert all(d >= "2026-01-01" and d <= "2026-01-31" for d in dates), \
        f"Dates outside filter range found: {[d for d in dates if d < '2026-01-01' or d > '2026-01-31']}"
    return f"{len(dates)} records in Jan 2026 ✓"

def test_api_weekly():
    data = get("/api/analytics/all/weekly")
    assert len(data["records"]) > 0, "no weekly records"
    r = data["records"][0]
    assert "year"   in r and "week" in r, "missing year/week fields"
    return f"{data['count']} weekly records"

def test_api_monthly():
    data = get("/api/analytics/all/monthly")
    assert len(data["records"]) > 0, "no monthly records"
    assert "month_name" in data["records"][0], "missing month_name field"
    return f"{data['count']} monthly records"

def test_api_peak_hours():
    data = get("/api/analytics/all/peak-hours", {"limit": 5})
    assert len(data["records"]) == 5, f"expected 5 peak hours, got {len(data['records'])}"
    assert "hour_label" in data["records"][0], "missing hour_label"
    return f"top hour: {data['records'][0]['hour_label']} ✓"

def test_api_total_cost():
    data = get("/api/analytics/total/cost")
    assert "grand_total_cost_EGP"   in data, "missing grand total cost"
    assert "per_device"             in data, "missing per_device"
    assert data["grand_total_cost_EGP"] > 0, "grand total is zero"
    assert all("share_of_total_pct" in d for d in data["per_device"]), \
        "some devices missing share_of_total_pct"
    shares = sum(d["share_of_total_pct"] for d in data["per_device"])
    assert abs(shares - 100.0) < 1.0, f"shares don't add up to ~100%: {shares}"
    return f"grand total = {data['grand_total_cost_EGP']} EGP, shares sum = {shares:.1f}%"

def test_api_anomalies():
    data = get("/api/analytics/anomalies")
    assert "alerts"          in data, "missing 'alerts'"
    assert "total_alerts"    in data, "missing 'total_alerts'"
    assert "severity_counts" in data, "missing 'severity_counts'"
    assert data["total_alerts"] > 0,  "no alerts found"
    if data["alerts"]:
        assert "severity" in data["alerts"][0], "alert missing 'severity' field"
    return f"{data['total_alerts']} alerts, rate={data['anomaly_rate_pct']}%"

def test_api_anomalies_severity_filter():
    for sev in ("critical", "high", "medium", "low"):
        data = get("/api/analytics/anomalies", {"severity": sev})
        # All returned alerts must match the requested severity
        for a in data["alerts"]:
            assert a["severity"] == sev, \
                f"Alert with severity '{a['severity']}' returned for filter '{sev}'"
    return "severity filter works for all 4 levels ✓"

def test_api_bill_estimate():
    data = get("/api/analytics/bill-estimate", {"days": 30})
    assert "projected_total_cost_EGP" in data, "missing projected cost"
    assert "per_device"               in data, "missing per_device"
    assert data["projected_total_cost_EGP"] > 0, "projected cost is zero"
    return f"30-day estimate = {data['projected_total_cost_EGP']} EGP"

def test_api_invalid_appliance():
    r = requests.get(f"{API_BASE}/api/analytics/nonexistent_device_xyz/daily", timeout=10)
    assert r.status_code == 404, f"Expected 404 for unknown device, got {r.status_code}"
    return "404 returned for unknown device ✓"

def test_api_invalid_date_format():
    r = requests.get(f"{API_BASE}/api/analytics/Microwave/daily",
                     params={"from": "01-01-2026"}, timeout=10)
    assert r.status_code == 400, f"Expected 400 for bad date format, got {r.status_code}"
    return "400 returned for bad date format ✓"

def test_api_invalid_severity():
    r = requests.get(f"{API_BASE}/api/analytics/anomalies",
                     params={"severity": "extreme"}, timeout=10)
    assert r.status_code == 400, f"Expected 400 for invalid severity, got {r.status_code}"
    return "400 returned for invalid severity ✓"

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 5 — UI endpoints
# ═══════════════════════════════════════════════════════════════════════════════

def test_ui_dashboard():
    data = get("/api/ui/dashboard")
    for key in ("kpi_cards", "cost_donut", "energy_trend",
                "peak_hours", "anomaly_summary", "recent_alerts"):
        assert key in data, f"dashboard missing '{key}'"
    assert len(data["kpi_cards"]) == 4,         "expected 4 KPI cards"
    assert len(data["cost_donut"]["labels"]) > 0, "cost_donut has no labels"
    assert len(data["energy_trend"]["labels"]) > 0, "energy_trend has no labels"
    return f"{len(data['kpi_cards'])} KPI cards, {len(data['cost_donut']['labels'])} devices in donut ✓"

def test_ui_dashboard_kpi_values():
    data  = get("/api/ui/dashboard")
    cards = {c["id"]: c for c in data["kpi_cards"]}
    assert cards["total_energy"]["value"]  > 0, "KPI total_energy is zero"
    assert cards["total_cost"]["value"]    > 0, "KPI total_cost is zero"
    assert cards["projected_bill"]["value"] > 0, "KPI projected_bill is zero"
    return "all KPI values > 0 ✓"

def test_ui_dashboard_chart_shape():
    data = get("/api/ui/dashboard")
    n_labels   = len(data["energy_trend"]["labels"])
    for ds in data["energy_trend"]["datasets"]:
        assert len(ds["data"]) == n_labels, \
            f"Dataset '{ds['label']}' has {len(ds['data'])} points but {n_labels} labels"
    assert len(data["peak_hours"]["datasets"][0]["data"]) == 24, \
        "peak_hours should have exactly 24 data points"
    return f"chart shapes consistent, {n_labels} trend labels, 24 peak-hour bars ✓"

def test_ui_energy_trend_daily():
    data = get("/api/ui/charts/energy-trend", {"granularity": "daily"})
    assert data["granularity"]                   == "daily", "wrong granularity"
    assert len(data["chart_data"]["labels"])      > 0,       "no labels"
    assert len(data["chart_data"]["datasets"])    > 0,       "no datasets"
    n = len(data["chart_data"]["labels"])
    for ds in data["chart_data"]["datasets"]:
        assert len(ds["data"]) == n, "Dataset length mismatch in daily trend"
    return f"{n} days, {len(data['chart_data']['datasets'])} device lines ✓"

def test_ui_energy_trend_monthly():
    data = get("/api/ui/charts/energy-trend", {"granularity": "monthly"})
    assert data["granularity"] == "monthly", "wrong granularity"
    assert len(data["chart_data"]["labels"]) >= 2, \
        f"Expected ≥ 2 months, got {len(data['chart_data']['labels'])}"
    return f"{len(data['chart_data']['labels'])} months ✓"

def test_ui_energy_trend_invalid():
    r = requests.get(f"{API_BASE}/api/ui/charts/energy-trend",
                     params={"granularity": "hourly"}, timeout=10)
    assert r.status_code == 400, f"Expected 400 for invalid granularity, got {r.status_code}"
    return "400 for invalid granularity ✓"

def test_ui_cost_breakdown():
    data = get("/api/ui/charts/cost-breakdown")
    assert "chart_data"  in data, "missing chart_data"
    assert "table_data"  in data, "missing table_data"
    n_devices = len(EXPECTED_DEVICES)
    assert len(data["chart_data"]["labels"]) == n_devices, \
        f"Expected {n_devices} devices, got {len(data['chart_data']['labels'])}"
    shares = sum(r["share_pct"] for r in data["table_data"])
    assert abs(shares - 100.0) < 1.0, f"shares don't add to ~100%: {shares}"
    ranks  = [r["rank"] for r in data["table_data"]]
    assert ranks == list(range(1, n_devices + 1)), f"ranks not sequential: {ranks}"
    return f"{n_devices} devices, shares sum = {shares:.1f}% ✓"

def test_ui_anomaly_feed():
    data = get("/api/ui/anomalies/feed")
    assert "alerts"           in data, "missing 'alerts'"
    assert "total"            in data, "missing 'total'"
    assert "severity_summary" in data, "missing 'severity_summary'"
    if data["alerts"]:
        a = data["alerts"][0]
        for field in ("severity", "severity_badge", "headline", "device_name"):
            assert field in a, f"alert missing field '{field}'"
        assert a["severity_badge"]["label"] in ("CRITICAL","HIGH","MEDIUM","LOW"), \
            f"unexpected badge label: {a['severity_badge']['label']}"
    return f"{data['total']} total alerts, {len(data['alerts'])} returned ✓"

def test_ui_anomaly_feed_pagination():
    page1 = get("/api/ui/anomalies/feed", {"limit": 3, "offset": 0})
    page2 = get("/api/ui/anomalies/feed", {"limit": 3, "offset": 3})
    if page1["total"] > 3:
        ids1 = [a["interval_start"] + a["device_name"] for a in page1["alerts"]]
        ids2 = [a["interval_start"] + a["device_name"] for a in page2["alerts"]]
        overlap = set(ids1) & set(ids2)
        assert not overlap, f"Pages overlap: {overlap}"
    return "pagination pages don't overlap ✓"

def test_ui_anomaly_heatmap():
    data = get("/api/ui/anomalies/heatmap")
    assert "devices" in data, "missing 'devices'"
    assert "dates"   in data, "missing 'dates'"
    assert "matrix"  in data, "missing 'matrix'"
    assert "series"  in data, "missing 'series'"
    assert len(data["matrix"]) == len(data["devices"]), \
        "matrix rows != number of devices"
    if data["matrix"] and data["dates"]:
        assert len(data["matrix"][0]) == len(data["dates"]), \
            "matrix columns != number of dates"
    return (f"{len(data['devices'])} devices × "
            f"{len(data['dates'])} days in heatmap ✓")

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 6 — HE layer (optional — skip if tenseal not installed)
# ═══════════════════════════════════════════════════════════════════════════════

def test_he_available():
    try:
        import tenseal as ts
        ctx = ts.context(ts.SCHEME_TYPE.CKKS, 8192, coeff_mod_bit_sizes=[60,40,40,60])
        ctx.global_scale = 2**40
        return f"TenSEAL {ts.__version__} available ✓"
    except ImportError:
        raise AssertionError("tenseal not installed — run: pip install tenseal")

def test_he_encrypt_decrypt():
    import tenseal as ts
    ctx = ts.context(ts.SCHEME_TYPE.CKKS, 8192, coeff_mod_bit_sizes=[60,40,40,60])
    ctx.generate_galois_keys()
    ctx.global_scale = 2**40
    original = [10.5, 20.3, 15.7, 8.1, 30.2]
    enc      = ts.ckks_vector(ctx, original)
    dec      = enc.decrypt()
    for o, d in zip(original, dec):
        assert abs(o - d) < 0.01, f"Decrypt error too large: {abs(o-d)}"
    return "encrypt → decrypt round-trip within 0.01 ✓"

def test_he_sum_correctness():
    import tenseal as ts
    ctx = ts.context(ts.SCHEME_TYPE.CKKS, 8192, coeff_mod_bit_sizes=[60,40,40,60])
    ctx.generate_galois_keys()
    ctx.global_scale = 2**40
    values   = [10.5, 20.3, 15.7, 8.1, 30.2]
    expected = sum(values)
    enc_sum  = ts.ckks_vector(ctx, values).sum().decrypt()[0]
    err_pct  = abs(enc_sum - expected) / expected * 100
    assert err_pct < 0.01, f"HE sum error {err_pct:.4f}% exceeds 0.01% tolerance"
    return f"HE sum={enc_sum:.4f}, plain={expected:.4f}, error={err_pct:.6f}% ✓"

def test_he_api_summary():
    r = requests.get(f"{API_BASE}/api/he/summary", timeout=HE_TIMEOUT)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    data = body["data"]
    assert "per_device"       in data, "missing 'per_device'"
    assert "scheme"           in data, "missing 'scheme'"
    assert "total_he_time_ms" in data, "missing timing info"
    assert len(data["per_device"]) == len(EXPECTED_DEVICES), \
        f"Expected {len(EXPECTED_DEVICES)} devices, got {len(data['per_device'])}"
    return f"{len(data['per_device'])} devices encrypted in {data['total_he_time_ms']:.0f}ms"

def test_he_api_verify():
    r = requests.get(f"{API_BASE}/api/he/verify", timeout=HE_TIMEOUT)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    data = body["data"]
    assert "all_correct"  in data, "missing 'all_correct'"
    assert "comparison"   in data, "missing 'comparison'"
    all_pass = all(r["within_tolerance"] for r in data["comparison"])
    assert all_pass, \
        f"HE results outside tolerance: {[r for r in data['comparison'] if not r['within_tolerance']]}"
    return f"all {len(data['comparison'])} devices within 0.01% tolerance ✓"

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 7 — Cross-layer consistency
# Verifies that API totals match what MongoDB actually contains.
# ═══════════════════════════════════════════════════════════════════════════════

def test_cross_total_energy_matches():
    client = pymongo.MongoClient(MONGO_URI)
    mongo_total = next(client[DB_NAME]["appliance_data"].aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$total_energy_kWh"}}}
    ]), {}).get("total", 0)

    api_total = get("/api/analytics/total/cost")["grand_total_energy_kWh"]

    err_pct = abs(mongo_total - api_total) / max(mongo_total, 1e-9) * 100
    assert err_pct < TOLERANCE_PCT, \
        f"Energy mismatch: MongoDB={mongo_total:.4f}, API={api_total:.4f} ({err_pct:.2f}%)"
    return f"MongoDB={mongo_total:.2f}kWh, API={api_total:.2f}kWh, diff={err_pct:.4f}% ✓"

def test_cross_total_cost_matches():
    client = pymongo.MongoClient(MONGO_URI)
    mongo_total = next(client[DB_NAME]["appliance_data"].aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$total_cost_EGP"}}}
    ]), {}).get("total", 0)

    api_total = get("/api/analytics/total/cost")["grand_total_cost_EGP"]

    err_pct = abs(mongo_total - api_total) / max(mongo_total, 1e-9) * 100
    assert err_pct < TOLERANCE_PCT, \
        f"Cost mismatch: MongoDB={mongo_total:.2f}, API={api_total:.2f} ({err_pct:.2f}%)"
    return f"MongoDB={mongo_total:.2f}EGP, API={api_total:.2f}EGP, diff={err_pct:.4f}% ✓"

def test_cross_alert_count_matches():
    client      = pymongo.MongoClient(MONGO_URI)
    mongo_count = client[DB_NAME]["anomaly_alerts"].count_documents({})
    api_count   = get("/api/analytics/anomalies")["total_alerts"]
    assert mongo_count == api_count, \
        f"Alert count mismatch: MongoDB={mongo_count}, API={api_count}"
    return f"both report {mongo_count} alerts ✓"

def test_cross_device_list_matches():
    client         = pymongo.MongoClient(MONGO_URI)
    mongo_devices  = sorted(client[DB_NAME]["appliance_data"].distinct("device_name"))
    api_devices    = sorted(d["device_name"] for d in get("/api/analytics/total/cost")["per_device"])
    assert mongo_devices == api_devices, \
        f"Device list mismatch:\nMongoDB: {mongo_devices}\nAPI:     {api_devices}"
    return f"both report same {len(mongo_devices)} devices ✓"

def test_cross_shares_sum_to_100():
    data   = get("/api/ui/charts/cost-breakdown")
    shares = sum(r["share_pct"] for r in data["table_data"])
    assert abs(shares - 100.0) < 1.0, f"Shares sum to {shares:.2f}% not ~100%"
    return f"shares sum = {shares:.2f}% ✓"

def test_cross_ui_dashboard_energy_matches_api():
    dashboard_energy = get("/api/ui/dashboard")["kpi_cards"]
    kpi = {c["id"]: c["value"] for c in dashboard_energy}
    api_energy = get("/api/analytics/total/cost")["grand_total_energy_kWh"]
    err_pct = abs(kpi["total_energy"] - api_energy) / max(api_energy, 1e-9) * 100
    assert err_pct < TOLERANCE_PCT, \
        f"Dashboard energy KPI ({kpi['total_energy']}) != /total/cost ({api_energy}), diff={err_pct:.2f}%"
    return f"dashboard KPI matches /total/cost within {err_pct:.4f}% ✓"

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — run all tests
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print(f"\n{bold('=' * 65)}")
    print(f"{bold('  Smart Home Energy System — End-to-End Test Suite')}")
    print(f"{bold('=' * 65)}")
    print(f"  API base:   {API_BASE}")
    print(f"  Models dir: {MODELS_DIR}")
    print(f"  Timestamp:  {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Layer 1 — MongoDB ──────────────────────────────────────────────────────
    section("Layer 1 — MongoDB Connectivity & Data Integrity")
    for name, fn in [
        ("MongoDB connects successfully",     test_mongo_connect),
        ("Required collections exist",        test_mongo_collections_exist),
        ("Record count ≥ 14,000",             test_mongo_record_count),
        ("All 5 devices present",             test_mongo_devices_present),
        ("Schema fields complete",            test_mongo_schema_fields),
        ("No null avg_power_W fields",        test_mongo_no_null_power),
        ("Ground-truth anomaly labels exist", test_mongo_anomaly_labels),
        ("anomaly_alerts written",            test_mongo_alerts_written),
        ("Alert schema fields complete",      test_mongo_alert_schema),
        ("Inference checkpoint written",      test_mongo_checkpoint_written),
    ]:
        run_test("MongoDB", name, fn)

    # ── Layer 2 — Feature engineering ─────────────────────────────────────────
    section("Layer 2 — Feature Engineering")
    for name, fn in [
        ("runtime_ratio = active_min / 30",   test_feature_runtime_ratio),
        ("power_x_runtime = power * ratio",   test_feature_power_x_runtime),
        ("Zero active_minutes handled",        test_feature_zero_active),
        ("No NaN in engineered features",      test_feature_no_nan),
        ("Feature values in valid ranges",     test_feature_values_in_range),
    ]:
        run_test("Features", name, fn)

    # ── Layer 3 — ML models ────────────────────────────────────────────────────
    section("Layer 3 — ML Model Files & Predictions")
    for name, fn in [
        ("All model .pkl files exist",         test_model_files_exist),
        ("training_metadata.pkl valid",        test_model_metadata),
        ("Features in sync across scripts",    test_model_feature_sync),
        ("Smoke test: predict on dummy row",   test_model_predict_smoke),
        ("Scaler dimensions correct",          test_model_scaler_dimensions),
        ("Contamination rate < 5%",            test_model_contamination_rate),
    ]:
        run_test("ML Models", name, fn)

    # ── Layer 4 — Core API ─────────────────────────────────────────────────────
    section("Layer 4 — Core API Endpoints")
    for name, fn in [
        ("GET /api/health",                       test_api_health),
        ("GET /api/analytics/summary",            test_api_summary),
        ("GET /daily returns records",            test_api_daily),
        ("GET /daily pagination works",           test_api_daily_pagination),
        ("GET /daily date filter works",          test_api_daily_date_filter),
        ("GET /weekly returns records",           test_api_weekly),
        ("GET /monthly with month_name",          test_api_monthly),
        ("GET /peak-hours returns 5",             test_api_peak_hours),
        ("GET /total/cost shares sum ~100%",      test_api_total_cost),
        ("GET /anomalies with severity field",    test_api_anomalies),
        ("GET /anomalies severity filter",        test_api_anomalies_severity_filter),
        ("GET /bill-estimate 30 days",            test_api_bill_estimate),
        ("404 for unknown device",                test_api_invalid_appliance),
        ("400 for bad date format",               test_api_invalid_date_format),
        ("400 for invalid severity",              test_api_invalid_severity),
    ]:
        run_test("Core API", name, fn)

    # ── Layer 5 — UI endpoints ─────────────────────────────────────────────────
    section("Layer 5 — UI-Ready Endpoints")
    for name, fn in [
        ("GET /api/ui/dashboard structure",       test_ui_dashboard),
        ("Dashboard KPI values > 0",              test_ui_dashboard_kpi_values),
        ("Dashboard chart shapes consistent",     test_ui_dashboard_chart_shape),
        ("GET /energy-trend daily",               test_ui_energy_trend_daily),
        ("GET /energy-trend monthly",             test_ui_energy_trend_monthly),
        ("GET /energy-trend rejects 'hourly'",    test_ui_energy_trend_invalid),
        ("GET /cost-breakdown shares + ranks",    test_ui_cost_breakdown),
        ("GET /anomalies/feed structure",         test_ui_anomaly_feed),
        ("GET /anomalies/feed pagination",        test_ui_anomaly_feed_pagination),
        ("GET /anomalies/heatmap matrix shape",   test_ui_anomaly_heatmap),
    ]:
        run_test("UI Endpoints", name, fn)

    # ── Layer 6 — HE layer ─────────────────────────────────────────────────────
    section("Layer 6 — Homomorphic Encryption (TenSEAL)")
    for name, fn in [
        ("TenSEAL importable",                    test_he_available),
        ("Encrypt → decrypt round-trip",          test_he_encrypt_decrypt),
        ("HE sum within 0.01% of plaintext",      test_he_sum_correctness),
        ("GET /api/he/summary returns all devices", test_he_api_summary),
        ("GET /api/he/verify all within tolerance", test_he_api_verify),
    ]:
        run_test("HE Layer", name, fn)

    # ── Layer 7 — Cross-layer consistency ──────────────────────────────────────
    section("Layer 7 — Cross-Layer Consistency")
    for name, fn in [
        ("Total energy: MongoDB == API",          test_cross_total_energy_matches),
        ("Total cost: MongoDB == API",            test_cross_total_cost_matches),
        ("Alert count: MongoDB == API",           test_cross_alert_count_matches),
        ("Device list: MongoDB == API",           test_cross_device_list_matches),
        ("Cost shares sum to ~100%",              test_cross_shares_sum_to_100),
        ("Dashboard energy KPI matches /total/cost", test_cross_ui_dashboard_energy_matches_api),
    ]:
        run_test("Consistency", name, fn)

    # ── Final report ───────────────────────────────────────────────────────────
    total   = len(results)
    passed  = sum(1 for _, _, ok, _ in results if ok)
    failed  = total - passed

    layer_summary = {}
    for layer, name, ok, msg in results:
        if layer not in layer_summary:
            layer_summary[layer] = {"pass": 0, "fail": 0}
        layer_summary[layer]["pass" if ok else "fail"] += 1

    print(f"\n{bold('=' * 65)}")
    print(f"{bold('  TEST RESULTS SUMMARY')}")
    print(f"{bold('=' * 65)}")

    for layer, counts in layer_summary.items():
        bar = green("█") * counts["pass"] + red("░") * counts["fail"]
        print(f"  {layer:<20} {bar}  "
              f"{green(str(counts['pass'])+' pass')}  "
              f"{(red(str(counts['fail'])+' fail')) if counts['fail'] else ''}")

    print(f"\n  Total:  {total} tests  |  "
          f"{green(str(passed)+' passed')}  |  "
          f"{red(str(failed)+' failed') if failed else green('0 failed')}")

    if failed == 0:
        print(f"\n  {green(bold('✅  ALL TESTS PASSED — System is demo-ready'))}")
    elif failed <= 3:
        print(f"\n  {yellow(bold('⚠️   MOSTLY PASSING — Fix the failures above before handover'))}")
    else:
        print(f"\n  {red(bold('❌  MULTIPLE FAILURES — System needs attention before handover'))}")

    print()
    sys.exit(0 if failed == 0 else 1)