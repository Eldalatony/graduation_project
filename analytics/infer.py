"""
infer.py
--------
Loads saved models from train.py and scores NEW incoming records only.
Writes detected anomalies to the `anomaly_alerts` collection in MongoDB.

Incremental logic fix:
  - Previous version tracked progress via the last ALERT's interval_start.
    Problem: if a batch has no anomalies, no alert is written, so the next
    run re-scores the same records all over again.
  - Fixed version writes a separate `infer_checkpoint` document after every
    run, recording the latest interval_start that was scored regardless of
    whether anomalies were found.

How to use:
  - Run on a schedule every 30 minutes (matching your data interval)
  - Each run scores only records newer than the last checkpoint
  - Detected anomalies appear in the `anomaly_alerts` collection

For real data:
  - No changes needed here as long as the schema stays consistent
  - Just retrain with train.py when switching to real data
"""

import os
import pymongo
import pandas as pd
import joblib
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────

MONGO_URI = "mongodb://admin:admin123@ac-smxdtmy-shard-00-00.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-01.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-02.nvratez.mongodb.net:27017/?ssl=true&replicaSet=atlas-12lqnf-shard-0&authSource=admin&appName=Cluster0"

MODELS_DIR = "models"

# Must be identical to train.py
FEATURES = [
    "avg_power_W",
    "max_power_W",
    "total_energy_kWh",
    "active_minutes",
    "idle_minutes",
    "runtime_ratio",
    "power_x_runtime",
]

# ── Feature engineering (identical to train.py) ───────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["runtime_ratio"]   = df["active_minutes"] / 30.0
    df["power_x_runtime"] = df["avg_power_W"] * df["runtime_ratio"]
    return df

# ── Connect ───────────────────────────────────────────────────────────────────

client         = pymongo.MongoClient(MONGO_URI)
db             = client["smart_home"]
collection     = db["appliance_data"]
alerts_col     = db["anomaly_alerts"]
checkpoint_col = db["infer_checkpoint"]   # tracks last scored interval

# ── Load training metadata ────────────────────────────────────────────────────

metadata_path = os.path.join(MODELS_DIR, "training_metadata.pkl")

if not os.path.exists(metadata_path):
    print("❌ No trained models found. Run train.py first.")
    exit()

metadata = joblib.load(metadata_path)
print(f"Models trained at: {metadata['trained_at']}")
print(f"Features used:     {metadata['features']}")
print(f"Devices covered:   {metadata['devices_trained']}\n")

# ── Find records not yet scored (fixed incremental logic) ─────────────────────

checkpoint = checkpoint_col.find_one(sort=[("scored_at", -1)])

if checkpoint:
    last_scored_interval = checkpoint["last_interval_start"]
    query_filter = {"interval_start": {"$gt": last_scored_interval}}
    print(f"Incremental mode: scoring records after {last_scored_interval}")
else:
    query_filter = {}
    print("First run: scoring all records in database")

records = list(collection.find(query_filter, {"_id": 0}))
print(f"Records to score: {len(records)}\n")

if not records:
    print("✅ No new records to score.")
    exit()

# ── Build DataFrame and engineer features ─────────────────────────────────────

df = pd.DataFrame(records)
df = engineer_features(df)

# ── Score per device ──────────────────────────────────────────────────────────

alerts_to_insert = []
scored_count     = 0

for device in df["device_name"].unique():
    model_path  = os.path.join(MODELS_DIR, f"{device.replace(' ', '_')}_model.pkl")
    scaler_path = os.path.join(MODELS_DIR, f"{device.replace(' ', '_')}_scaler.pkl")

    if not os.path.exists(model_path):
        print(f"  ⚠️  No model found for '{device}' — skipping (run train.py first)")
        continue

    model  = joblib.load(model_path)
    scaler = joblib.load(scaler_path)

    device_df = df[df["device_name"] == device].copy()
    X         = device_df[FEATURES].fillna(0)
    X_scaled  = scaler.transform(X)

    predictions    = model.predict(X_scaled)
    anomaly_scores = model.decision_function(X_scaled)

    device_df["model_predicted"] = (predictions == -1).astype(int)
    device_df["anomaly_score"]   = anomaly_scores

    detected      = device_df[device_df["model_predicted"] == 1]
    scored_count += len(device_df)

    for _, row in detected.iterrows():
        alert = {
            # Identity
            "gateway_id":  row.get("gateway_id",  "unknown"),
            "node_key":    row.get("node_key",    "unknown"),
            "device_name": row["device_name"],
            "device_type": row.get("device_type", "unknown"),
            # Time window
            "interval_start": row["interval_start"],
            "interval_end":   row.get("interval_end", ""),
            # Sensor readings
            "avg_power_W":      row["avg_power_W"],
            "max_power_W":      row["max_power_W"],
            "min_power_W":      row.get("min_power_W", 0),
            "total_energy_kWh": row["total_energy_kWh"],
            "total_cost_EGP":   row.get("total_cost_EGP", 0),
            "active_minutes":   row["active_minutes"],
            "idle_minutes":     row["idle_minutes"],
            "runtime_ratio":    round(float(row["runtime_ratio"]),   4),
            "power_x_runtime":  round(float(row["power_x_runtime"]), 4),
            # Detection metadata
            "anomaly_score": round(float(row["anomaly_score"]), 6),
            "scored_at":     datetime.now(timezone.utc).isoformat(),
            # Ground truth label (None for real data)
            "ground_truth_anomaly": row.get("anomaly", None),
        }
        alerts_to_insert.append(alert)

# ── Write alerts and checkpoint ───────────────────────────────────────────────

if alerts_to_insert:
    alerts_col.insert_many(alerts_to_insert)
    print(f"🚨 {len(alerts_to_insert)} anomaly alerts written to `anomaly_alerts` collection")
else:
    print("✅ No anomalies detected in this batch")

print(f"   Records scored: {scored_count}")
print(f"   Alert rate:     {len(alerts_to_insert)/max(scored_count,1)*100:.2f}%")

# Save checkpoint — tracks last interval scored regardless of anomaly outcome
latest_interval = df["interval_start"].max()
checkpoint_col.insert_one({
    "last_interval_start": latest_interval,
    "scored_at":           datetime.now(timezone.utc).isoformat(),
    "records_scored":      scored_count,
    "alerts_raised":       len(alerts_to_insert),
})
print(f"   Checkpoint saved: last scored interval = {latest_interval}")

# ── Print recent alerts ───────────────────────────────────────────────────────

recent = list(alerts_col.find({}, {"_id": 0}).sort("scored_at", -1).limit(20))

if recent:
    print(f"\n📋 Most recent alerts (last {len(recent)}):\n")
    print(f"  {'Device':<25} {'Interval':<22} {'Avg W':>7} {'Max W':>7} "
          f"{'Act Min':>7} {'Score':>9}  Ground Truth")
    print("  " + "-" * 100)
    for a in recent:
        gt = a.get("ground_truth_anomaly") or "—"
        print(
            f"  {a['device_name']:<25} "
            f"{a['interval_start']:<22} "
            f"{a['avg_power_W']:>7.1f} "
            f"{a['max_power_W']:>7.1f} "
            f"{a['active_minutes']:>7} "
            f"{a['anomaly_score']:>9.5f}  "
            f"{gt}"
        )