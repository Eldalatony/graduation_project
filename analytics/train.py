"""
train.py
--------
Trains one Isolation Forest model per device on historical data.
Saves each model + scaler to the /models directory.

Feature design rationale:
  - Isolation Forest works by randomly splitting feature space.
  - Fewer, high-signal features outperform many noisy ones for this algorithm.
  - Time-based features (hour, weekend) hurt performance because Isolation Forest
    treats them as isolation axes rather than context — removed.
  - Rolling baseline features cause NaN pollution in early records — removed.
  - runtime_ratio and power_x_runtime are the two most effective additions
    because they amplify the excessive_runtime pattern that was previously 0%.

When real data arrives:
  1. Collect 2-4 weeks of confirmed-normal readings first
  2. Run this script — it will overwrite the simulated models
  3. Adjust CONTAMINATION to match your expected real fault rate
  4. Everything else (infer.py, analytics.py) stays unchanged
"""

import os
import pymongo
import pandas as pd
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────

MONGO_URI = "mongodb://admin:admin123@ac-smxdtmy-shard-00-00.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-01.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-02.nvratez.mongodb.net:27017/?ssl=true&replicaSet=atlas-12lqnf-shard-0&authSource=admin&appName=Cluster0"

MODELS_DIR = "models"

# Core features — do NOT add time-based or rolling features to Isolation Forest.
# Each feature carries direct fault signal:
#   avg_power_W       — detects power_spike and stuck_on
#   max_power_W       — catches instantaneous spikes avg might smooth over
#   total_energy_kWh  — correlated with power but independent scaling helps
#   active_minutes    — direct signal for excessive_runtime
#   idle_minutes      — inverse of active; stabilises the forest
#   runtime_ratio     — active_minutes / 30, amplifies excessive_runtime signal
#   power_x_runtime   — avg_power * runtime_ratio: "high power AND long duration"
#                        This is the key feature for catching excessive_runtime
FEATURES = [
    "avg_power_W",
    "max_power_W",
    "total_energy_kWh",
    "active_minutes",
    "idle_minutes",
    "runtime_ratio",
    "power_x_runtime",
]

# Anomaly rate: 40 injected / 14400 records = 0.00278
# For real data: set to (expected faults per period) / (total intervals per period)
CONTAMINATION = 0.003

# ── Setup ─────────────────────────────────────────────────────────────────────

os.makedirs(MODELS_DIR, exist_ok=True)

client     = pymongo.MongoClient(MONGO_URI)
db         = client["smart_home"]
collection = db["appliance_data"]

# Indexes for faster queries — safe to run repeatedly (no-op if already exist)
collection.create_index([("device_name", 1), ("interval_start", 1)])
collection.create_index([("interval_start", 1)])
print("✅ MongoDB indexes ensured")

# ── Feature engineering ───────────────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pure arithmetic feature derivation — no rolling windows, no time parsing.
    NaN-free and identical between training and inference.
    """
    df = df.copy()
    df["runtime_ratio"]   = df["active_minutes"] / 30.0
    df["power_x_runtime"] = df["avg_power_W"] * df["runtime_ratio"]
    return df

# ── Load data ─────────────────────────────────────────────────────────────────

print("\nLoading data from MongoDB...")
data = list(collection.find({}, {"_id": 0}))
df   = pd.DataFrame(data)

print(f"Total records loaded: {len(df)}")

if df.empty:
    print("❌ No data found. Exiting.")
    exit()

df.rename(columns={"anomaly": "ground_truth_anomaly"}, inplace=True)
df["is_true_anomaly"] = df["ground_truth_anomaly"].apply(
    lambda x: 1 if (x is not None and str(x) not in ("None", "nan", "")) else 0
)
print(f"Ground-truth anomalies in dataset: {df['is_true_anomaly'].sum()}")

df = engineer_features(df)

# ── Train one model per device ────────────────────────────────────────────────

print(f"\nTraining models  (contamination={CONTAMINATION})...\n")

all_results = []

for device in sorted(df["device_name"].unique()):
    device_df = df[df["device_name"] == device].copy()

    if len(device_df) < 50:
        print(f"  ⚠️  {device}: skipped ({len(device_df)} records — need ≥ 50)")
        continue

    X        = device_df[FEATURES].fillna(0)
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=300,
        contamination=CONTAMINATION,
        max_features=len(FEATURES),
        random_state=42
    )
    model.fit(X_scaled)

    model_path  = os.path.join(MODELS_DIR, f"{device.replace(' ', '_')}_model.pkl")
    scaler_path = os.path.join(MODELS_DIR, f"{device.replace(' ', '_')}_scaler.pkl")
    joblib.dump(model,  model_path)
    joblib.dump(scaler, scaler_path)

    device_df["anomaly_score"]   = model.decision_function(X_scaled)
    device_df["model_predicted"] = (model.predict(X_scaled) == -1).astype(int)

    tp = ((device_df["is_true_anomaly"] == 1) & (device_df["model_predicted"] == 1)).sum()
    fp = ((device_df["is_true_anomaly"] == 0) & (device_df["model_predicted"] == 1)).sum()
    fn = ((device_df["is_true_anomaly"] == 1) & (device_df["model_predicted"] == 0)).sum()

    print(f"  ✅ {device:<25} | records: {len(device_df):>5} | "
          f"true anomalies: {device_df['is_true_anomaly'].sum():>2} | "
          f"TP: {tp:>2}  FP: {fp:>2}  FN: {fn:>2} | saved → {model_path}")

    all_results.append(device_df)

# ── Overall evaluation ─────────────────────────────────────────────────────────

df_all = pd.concat(all_results).reset_index(drop=True)
y_true = df_all["is_true_anomaly"]
y_pred = df_all["model_predicted"]

print("\n" + "=" * 60)
print("📊 OVERALL MODEL EVALUATION")
print("=" * 60)
print("\nConfusion Matrix (rows=actual, cols=predicted | 0=normal 1=anomaly):\n")
print(confusion_matrix(y_true, y_pred))
print("\nClassification Report:\n")
print(classification_report(y_true, y_pred, target_names=["Normal", "Anomaly"]))

# ── Save metadata ──────────────────────────────────────────────────────────────

metadata = {
    "trained_at":             datetime.now(timezone.utc).isoformat(),
    "total_records":          int(len(df)),
    "contamination":          CONTAMINATION,
    "features":               FEATURES,
    "devices_trained":        sorted(df["device_name"].unique().tolist()),
    "ground_truth_anomalies": int(df["is_true_anomaly"].sum()),
}
joblib.dump(metadata, os.path.join(MODELS_DIR, "training_metadata.pkl"))
print(f"\n📁 Training metadata saved → {MODELS_DIR}/training_metadata.pkl")
print("✅ Training complete. Run infer.py to score new data.")