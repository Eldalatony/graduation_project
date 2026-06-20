"""
model_manager.py
----------------
The adaptive per-device lifecycle brain.

Every device monitored by the system goes through:

    NEW  ──▶  LEARNING (warm-up)  ──▶  READY
              collect baseline,        model trained on THIS device's
              no predictions           own normal pattern → scoring on

A device only becomes READY once it has accumulated enough data over enough
time (see shared.READY_* thresholds). This is the permanent rule for every
device — unsupervised, no labels, no per-device-type assumptions.

State + the trained model live in the `device_models` Mongo collection (one
doc per device), so models are created at runtime and survive rebuilds.
"""

import logging
import pandas as pd
from datetime import datetime, timezone

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from shared import (
    device_models_col, FEATURES, INTERVAL_MINUTES,
    READY_MIN_RECORDS, READY_MIN_SPAN_DAYS, READY_MIN_ACTIVE_FRACTION,
    CONTAMINATION, N_ESTIMATORS, RETRAIN_INTERVAL_DAYS,
    serialize_model, deserialize_model,
)
from classifier import compute_baseline

log = logging.getLogger("analytics.model_manager")


# ── Feature engineering (single source of truth — infer/evaluate import this) ───
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Pure arithmetic derivation. NaN-free, identical at train and inference."""
    df = df.copy()
    df["runtime_ratio"]   = df["active_minutes"] / float(INTERVAL_MINUTES)
    df["power_x_runtime"] = df["avg_power_W"] * df["runtime_ratio"]
    return df


# ── Progress / readiness ────────────────────────────────────────────────────────
def compute_progress(device_df: pd.DataFrame) -> dict:
    """How much usable data a device has collected so far."""
    n = len(device_df)
    if n == 0:
        return {"n_records": 0, "span_days": 0.0, "active_fraction": 0.0,
                "first_interval": None, "last_interval": None}

    times = pd.to_datetime(device_df["interval_start"], utc=True, errors="coerce").dropna()
    if len(times) >= 2:
        span_days = (times.max() - times.min()).total_seconds() / 86400.0
    else:
        span_days = 0.0

    active_fraction = float((device_df["active_minutes"] > 0).mean())

    return {
        "n_records":       int(n),
        "span_days":       round(span_days, 2),
        "active_fraction": round(active_fraction, 3),
        "first_interval":  str(times.min().isoformat()) if len(times) else None,
        "last_interval":   str(times.max().isoformat()) if len(times) else None,
    }


def is_ready(progress: dict) -> tuple:
    """Returns (ready: bool, reasons: list[str]) — all conditions must pass."""
    reasons = []
    if progress["n_records"] < READY_MIN_RECORDS:
        reasons.append(f"needs {READY_MIN_RECORDS} records (has {progress['n_records']})")
    if progress["span_days"] < READY_MIN_SPAN_DAYS:
        reasons.append(f"needs {READY_MIN_SPAN_DAYS}d span (has {progress['span_days']}d)")
    if progress["active_fraction"] < READY_MIN_ACTIVE_FRACTION:
        reasons.append(f"too idle ({progress['active_fraction']*100:.1f}% active)")
    return (len(reasons) == 0, reasons)


def progress_pct(progress: dict) -> float:
    """0–100% toward readiness — min of the two main gates, for the UI."""
    by_records = progress["n_records"] / READY_MIN_RECORDS if READY_MIN_RECORDS else 1
    by_span    = progress["span_days"] / READY_MIN_SPAN_DAYS if READY_MIN_SPAN_DAYS else 1
    return round(min(1.0, by_records, by_span) * 100, 1)


# ── State access ────────────────────────────────────────────────────────────────
def get_state(device_name: str) -> dict | None:
    return device_models_col.find_one({"device_name": device_name})


def _state_public(doc: dict) -> dict:
    """Strip the heavy model blobs for API/log responses."""
    if not doc:
        return None
    return {
        "device_name":         doc["device_name"],
        "status":              doc.get("status", "learning"),
        "progress_pct":        doc.get("progress_pct", 0),
        "n_records":           doc.get("n_records", 0),
        "span_days":           doc.get("span_days", 0),
        "active_fraction":     doc.get("active_fraction", 0),
        "readiness_reasons":   doc.get("readiness_reasons", []),
        "trained_at":          doc.get("trained_at"),
        "trained_on_records":  doc.get("trained_on_records"),
        "last_scored_interval": doc.get("last_scored_interval"),
        "updated_at":          doc.get("updated_at"),
    }


def update_learning_state(device_name: str, progress: dict, reasons: list):
    device_models_col.update_one(
        {"device_name": device_name},
        {"$set": {
            "status":            "learning",
            "n_records":         progress["n_records"],
            "span_days":         progress["span_days"],
            "active_fraction":   progress["active_fraction"],
            "progress_pct":      progress_pct(progress),
            "readiness_reasons": reasons,
            "first_interval":    progress["first_interval"],
            "last_interval":     progress["last_interval"],
            "updated_at":        datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )


# ── Training ─────────────────────────────────────────────────────────────────────
def train_device(device_name: str, device_df: pd.DataFrame) -> dict:
    """
    Fit an Isolation Forest + scaler on a device's full history (unsupervised),
    store both in Mongo, and flip the device to READY. Re-callable for refresh.
    """
    progress = compute_progress(device_df)
    df = engineer_features(device_df)
    X  = df[FEATURES].fillna(0)

    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=CONTAMINATION,
        max_features=len(FEATURES),
        random_state=42,
    )
    model.fit(X_scaled)

    # Per-device normal baseline — used by the rule layer to *label* anomalies.
    baseline = compute_baseline(df)

    now = datetime.now(timezone.utc).isoformat()
    device_models_col.update_one(
        {"device_name": device_name},
        {"$set": {
            "status":             "ready",
            "model_blob":         serialize_model(model),
            "scaler_blob":        serialize_model(scaler),
            "feature_order":      FEATURES,
            "baseline":           baseline,
            "contamination":      CONTAMINATION,
            "n_estimators":       N_ESTIMATORS,
            "n_records":          progress["n_records"],
            "span_days":          progress["span_days"],
            "active_fraction":    progress["active_fraction"],
            "progress_pct":       100.0,
            "readiness_reasons":  [],
            "trained_at":         now,
            "trained_on_records": progress["n_records"],
            "trained_on_span_days": progress["span_days"],
            "first_interval":     progress["first_interval"],
            "last_interval":      progress["last_interval"],
            "updated_at":         now,
        }},
        upsert=True,
    )
    log.info(f"✅ Trained '{device_name}' on {progress['n_records']} records "
             f"({progress['span_days']}d span) → READY")
    return {"device_name": device_name, "status": "ready", **progress}


def load_device_model(device_name: str):
    """Returns (model, scaler, feature_order) or (None, None, None) if not ready."""
    doc = device_models_col.find_one({"device_name": device_name})
    if not doc or doc.get("status") != "ready" or "model_blob" not in doc:
        return None, None, None
    model  = deserialize_model(doc["model_blob"])
    scaler = deserialize_model(doc["scaler_blob"])
    return model, scaler, doc.get("feature_order", FEATURES)


def should_retrain(state: dict, progress: dict) -> bool:
    """Refresh a ready model when enough new data has arrived since last train."""
    if not state or state.get("status") != "ready":
        return False
    trained_at = state.get("trained_at")
    if not trained_at:
        return True
    try:
        age_days = (datetime.now(timezone.utc) -
                    pd.to_datetime(trained_at, utc=True).to_pydatetime()).total_seconds() / 86400.0
    except Exception:
        return False
    grew = progress["n_records"] >= (state.get("trained_on_records", 0) + READY_MIN_RECORDS // 2)
    return age_days >= RETRAIN_INTERVAL_DAYS and grew


def set_checkpoint(device_name: str, last_interval: str):
    device_models_col.update_one(
        {"device_name": device_name},
        {"$set": {"last_scored_interval": last_interval,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
    )


def all_device_status() -> list:
    return [_state_public(d) for d in device_models_col.find({})]
