"""
shared.py
---------
Single source of truth for the analytics service:
  - MongoDB connection (driven by env vars, shared across all modules)
  - Severity thresholds and helpers (used by api.py + api_ui_endpoints.py)

Every other module in py-files/ should import from here instead of
re-declaring its own MongoClient or severity logic.
"""

import os
import io
import pymongo
import joblib
from bson.binary import Binary

# ── MongoDB connection ────────────────────────────────────────────────────────
# Inside Docker the hostname `mongodb` resolves to the shemms_mongodb container.
# Locally (running scripts directly) override MONGO_URI in your shell.
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongodb:27017/shemms")
DB_NAME   = os.environ.get("MONGO_DB",  "shemms")

client          = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db              = client[DB_NAME]
data_col          = db["appliance_data"]
alerts_col        = db["anomaly_alerts"]
checkpoint_col    = db["infer_checkpoint"]
# One document per device: lifecycle state + the trained model itself.
# Lives in Mongo (not the image) so models are created at runtime, survive
# container rebuilds, and never need manual training.
device_models_col = db["device_models"]

# ── Severity classification ───────────────────────────────────────────────────
# anomaly_score from Isolation Forest is negative; more negative = more anomalous
SEVERITY_THRESHOLDS = {
    "critical": -0.07,
    "high":     -0.04,
    "medium":   -0.015,
    "low":       0.0,
}

SEVERITY_COLORS = {
    "critical": "#ef4444",
    "high":     "#f97316",
    "medium":   "#eab308",
    "low":      "#3b82f6",
}

DEVICE_COLORS = [
    "#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#ef4444",
    "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#84cc16",
]


def score_to_severity(score: float) -> str:
    if score <= SEVERITY_THRESHOLDS["critical"]:
        return "critical"
    if score <= SEVERITY_THRESHOLDS["high"]:
        return "high"
    if score <= SEVERITY_THRESHOLDS["medium"]:
        return "medium"
    return "low"


# ── ML constants ──────────────────────────────────────────────────────────────
# Length of one aggregation interval. Backend ETL produces hourly buckets (60),
# the synthetic seed produces 30-min buckets. Override via env if you switch.
INTERVAL_MINUTES = int(os.environ.get("INTERVAL_MINUTES", "60"))

MODELS_DIR = os.environ.get(
    "MODELS_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))
)

FEATURES = [
    "avg_power_W",
    "max_power_W",
    "total_energy_kWh",
    "active_minutes",
    "idle_minutes",
    "runtime_ratio",
    "power_x_runtime",
]

# ── Adaptive readiness gate ─────────────────────────────────────────────────────
# A device only graduates from LEARNING → READY (and starts producing anomaly
# predictions) once it has collected enough data over a long enough span. This is
# the permanent production rule — it applies to every device. Generating a test
# dataset simply satisfies these thresholds instantly instead of waiting in real
# time; it does NOT bypass the gate.
READY_MIN_RECORDS         = int(os.environ.get("READY_MIN_RECORDS", "200"))      # ≈ 8+ days of hourly data
READY_MIN_SPAN_DAYS       = float(os.environ.get("READY_MIN_SPAN_DAYS", "14"))   # must cover ≥ 2 weeks
READY_MIN_ACTIVE_FRACTION = float(os.environ.get("READY_MIN_ACTIVE_FRACTION", "0.02"))  # not a device that was simply off

# Isolation Forest is unsupervised: it learns each device's "normal" and flags
# outliers. contamination = expected fraction of anomalous intervals.
CONTAMINATION         = float(os.environ.get("CONTAMINATION", "0.02"))
N_ESTIMATORS          = int(os.environ.get("N_ESTIMATORS", "200"))
# Refresh a ready model periodically so it adapts as more data accumulates.
RETRAIN_INTERVAL_DAYS = float(os.environ.get("RETRAIN_INTERVAL_DAYS", "7"))


# ── Model (de)serialisation for Mongo storage ───────────────────────────────────
def serialize_model(obj) -> Binary:
    """joblib-dump any sklearn object to BSON Binary for storage in Mongo."""
    buf = io.BytesIO()
    joblib.dump(obj, buf)
    return Binary(buf.getvalue())


def deserialize_model(blob):
    """Inverse of serialize_model — load an sklearn object from BSON Binary."""
    return joblib.load(io.BytesIO(bytes(blob)))
