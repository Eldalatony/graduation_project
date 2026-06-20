"""
infer.py
--------
The adaptive inference tick. Runs on a schedule (app.py) or manually (CLI).

For every device in appliance_data:
  • LEARNING  → check readiness; if met, auto-train and flip to READY.
  • READY     → score records newer than the device's checkpoint, raise alerts,
                periodically refresh the model as more data accumulates.

No global model, no baked-in models, no labels. Each device learns its own
"normal" and is scored only once it has earned READY status.
"""

import logging
import pandas as pd
from datetime import datetime, timezone

from shared import data_col, alerts_col, score_to_severity
from classifier import compute_baseline, classify_anomaly
from model_manager import (
    engineer_features, compute_progress, is_ready, progress_pct,
    get_state, update_learning_state, train_device,
    load_device_model, should_retrain, set_checkpoint,
)
from forecaster import train_forecaster

log = logging.getLogger("analytics.infer")


def _safe_train_forecaster(device_name: str, device_df: pd.DataFrame):
    """Forecasting is a secondary feature — never let it break the critical
    anomaly-detection path. Train it alongside the detector, but swallow errors."""
    try:
        train_forecaster(device_name, device_df)
    except Exception as ex:
        log.warning(f"forecaster training failed for '{device_name}': {ex}")


def _score_device(device_name: str, device_df: pd.DataFrame, last_scored: str,
                  baseline: dict | None = None) -> int:
    """Score records newer than last_scored; upsert alerts. Returns alert count."""
    model, scaler, features = load_device_model(device_name)
    if model is None:
        return 0

    # Baseline of this device's normal behaviour, used to *label* anomalies.
    if baseline is None:
        baseline = compute_baseline(device_df)

    # Only score intervals we haven't scored yet (None → score full history once).
    if last_scored:
        new_df = device_df[device_df["interval_start"] > last_scored].copy()
    else:
        new_df = device_df.copy()
    if new_df.empty:
        return 0

    df = engineer_features(new_df)
    X  = df[features].fillna(0)
    df["anomaly_score"]   = model.decision_function(scaler.transform(X))
    df["model_predicted"] = (model.predict(scaler.transform(X)) == -1).astype(int)

    detected = df[df["model_predicted"] == 1]
    now = datetime.now(timezone.utc).isoformat()

    for _, row in detected.iterrows():
        anomaly_type = classify_anomaly(
            float(row["avg_power_W"]), float(row["max_power_W"]),
            int(row["active_minutes"]), float(row["runtime_ratio"]), baseline,
        )
        # Upsert keyed by (device, interval) so re-scoring never duplicates alerts.
        alerts_col.update_one(
            {"device_name": device_name, "interval_start": row["interval_start"]},
            {"$set": {
                "gateway_id":           row.get("gateway_id", "unknown"),
                "node_key":             row.get("node_key", "unknown"),
                "device_name":          device_name,
                "device_type":          row.get("device_type", "unknown"),
                "appliance_id":         row.get("appliance_id"),
                "user_id":              row.get("user_id"),
                "interval_start":       row["interval_start"],
                "interval_end":         row.get("interval_end", ""),
                "avg_power_W":          float(row["avg_power_W"]),
                "max_power_W":          float(row["max_power_W"]),
                "min_power_W":          float(row.get("min_power_W", 0)),
                "total_energy_kWh":     float(row["total_energy_kWh"]),
                "total_cost_EGP":       float(row.get("total_cost_EGP", 0)),
                "active_minutes":       int(row["active_minutes"]),
                "idle_minutes":         int(row["idle_minutes"]),
                "runtime_ratio":        round(float(row["runtime_ratio"]), 4),
                "power_x_runtime":      round(float(row["power_x_runtime"]), 4),
                "anomaly_score":        round(float(row["anomaly_score"]), 6),
                "severity":             score_to_severity(float(row["anomaly_score"])),
                "anomaly_type":         anomaly_type,
                "scored_at":            now,
                "ground_truth_anomaly": row.get("anomaly", None),
            }},
            upsert=True,
        )

    # Advance the checkpoint to the newest interval we just saw.
    set_checkpoint(device_name, str(new_df["interval_start"].max()))
    return len(detected)


def run_inference() -> dict:
    """One adaptive tick across all devices. Returns a summary for logging."""
    devices = data_col.distinct("device_name")
    summary = {"ready": [], "learning": [], "trained": [], "alerts_raised": 0}

    for device in devices:
        records = list(data_col.find({"device_name": device}, {"_id": 0}))
        if not records:
            continue
        device_df = pd.DataFrame(records).sort_values("interval_start")
        progress  = compute_progress(device_df)
        state     = get_state(device)
        ready     = bool(state and state.get("status") == "ready")

        # ── LEARNING: gate check ──────────────────────────────────────────────
        if not ready:
            ok, reasons = is_ready(progress)
            if ok:
                train_device(device, device_df)
                _safe_train_forecaster(device, device_df)
                summary["trained"].append(device)
                state, ready = get_state(device), True
            else:
                update_learning_state(device, progress, reasons)
                summary["learning"].append({"device": device, "pct": progress_pct(progress)})
                continue

        # ── READY: optional refresh, then score new data ──────────────────────
        if should_retrain(state, progress):
            train_device(device, device_df)
            _safe_train_forecaster(device, device_df)
            state = get_state(device)

        baseline = state.get("baseline") or compute_baseline(device_df)
        raised = _score_device(device, device_df, state.get("last_scored_interval"), baseline)
        summary["alerts_raised"] += raised
        summary["ready"].append({"device": device, "new_alerts": raised})

    log.info(f"tick: {len(summary['ready'])} ready, {len(summary['learning'])} learning, "
             f"{len(summary['trained'])} newly trained, {summary['alerts_raised']} alerts")
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
    result = run_inference()
    print(f"\nResult: {result}\n")
