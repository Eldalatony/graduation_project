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

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongodb:27017/shemms")
DB_NAME   = os.environ.get("MONGO_DB",  "shemms")

client          = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db              = client[DB_NAME]
data_col          = db["appliance_data"]
alerts_col        = db["anomaly_alerts"]
checkpoint_col    = db["infer_checkpoint"]
device_models_col = db["device_models"]

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

INTERVAL_MINUTES = int(os.environ.get("INTERVAL_MINUTES", "60"))

FEATURES = [
    "avg_power_W",
    "max_power_W",
    "total_energy_kWh",
    "active_minutes",
    "idle_minutes",
    "runtime_ratio",
    "power_x_runtime",
]

READY_MIN_RECORDS         = int(os.environ.get("READY_MIN_RECORDS", "200"))
READY_MIN_SPAN_DAYS       = float(os.environ.get("READY_MIN_SPAN_DAYS", "14"))
READY_MIN_ACTIVE_FRACTION = float(os.environ.get("READY_MIN_ACTIVE_FRACTION", "0.02"))

CONTAMINATION         = float(os.environ.get("CONTAMINATION", "0.02"))
N_ESTIMATORS          = int(os.environ.get("N_ESTIMATORS", "200"))
RETRAIN_INTERVAL_DAYS = float(os.environ.get("RETRAIN_INTERVAL_DAYS", "7"))

def serialize_model(obj) -> Binary:
    """joblib-dump any sklearn object to BSON Binary for storage in Mongo."""
    buf = io.BytesIO()
    joblib.dump(obj, buf)
    return Binary(buf.getvalue())

def deserialize_model(blob):
    """Inverse of serialize_model — load an sklearn object from BSON Binary."""
    return joblib.load(io.BytesIO(bytes(blob)))
