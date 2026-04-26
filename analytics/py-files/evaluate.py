"""
evaluate.py
-----------
Comprehensive model evaluation against ground-truth anomaly labels.

Only meaningful when ground-truth labels exist (simulated data, or real data
where faults have been manually confirmed and labeled).

For real data without labels:
  - Use alert rate and operator feedback as your quality signal
  - When operators confirm or reject alerts, log those decisions and use them
    to periodically retrain with soft labels
"""

import os
import pymongo
import pandas as pd
import joblib
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score

# ── Config ────────────────────────────────────────────────────────────────────

MONGO_URI = "mongodb://admin:admin123@ac-smxdtmy-shard-00-00.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-01.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-02.nvratez.mongodb.net:27017/?ssl=true&replicaSet=atlas-12lqnf-shard-0&authSource=admin&appName=Cluster0"

MODELS_DIR = "models"

# Must be identical to train.py and infer.py
FEATURES = [
    "avg_power_W",
    "max_power_W",
    "total_energy_kWh",
    "active_minutes",
    "idle_minutes",
    "runtime_ratio",
    "power_x_runtime",
]

# ── Feature engineering (identical to train.py and infer.py) ─────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["runtime_ratio"]   = df["active_minutes"] / 30.0
    df["power_x_runtime"] = df["avg_power_W"] * df["runtime_ratio"]
    return df

# ── Connect and load ──────────────────────────────────────────────────────────

client     = pymongo.MongoClient(MONGO_URI)
db         = client["smart_home"]
collection = db["appliance_data"]
alerts_col = db["anomaly_alerts"]

print("Loading data...")
data = list(collection.find({}, {"_id": 0}))
df   = pd.DataFrame(data)

print(f"Total records: {len(df)}")

if "anomaly" not in df.columns or df["anomaly"].isna().all():
    print("⚠️  No ground-truth labels found — evaluation skipped.")
    print("   This is expected for real data without manually labeled faults.")
    exit()

df.rename(columns={"anomaly": "ground_truth_anomaly"}, inplace=True)
df["is_true_anomaly"] = df["ground_truth_anomaly"].apply(
    lambda x: 1 if (x is not None and str(x) not in ("None", "nan", "")) else 0
)

print(f"True anomalies:  {df['is_true_anomaly'].sum()} "
      f"({df['is_true_anomaly'].mean()*100:.3f}% of all records)\n")

df = engineer_features(df)

# ── Score using saved models ──────────────────────────────────────────────────

all_results = []

for device in sorted(df["device_name"].unique()):
    model_path  = os.path.join(MODELS_DIR, f"{device.replace(' ', '_')}_model.pkl")
    scaler_path = os.path.join(MODELS_DIR, f"{device.replace(' ', '_')}_scaler.pkl")

    if not os.path.exists(model_path):
        print(f"  ⚠️  No saved model for '{device}' — run train.py first")
        continue

    model  = joblib.load(model_path)
    scaler = joblib.load(scaler_path)

    device_df = df[df["device_name"] == device].copy()
    X         = device_df[FEATURES].fillna(0)
    X_scaled  = scaler.transform(X)

    device_df["anomaly_score"]   = model.decision_function(X_scaled)
    device_df["model_predicted"] = (model.predict(X_scaled) == -1).astype(int)

    all_results.append(device_df)

df_all  = pd.concat(all_results).reset_index(drop=True)
y_true  = df_all["is_true_anomaly"]
y_pred  = df_all["model_predicted"]
y_score = -df_all["anomaly_score"]

# ── Overall metrics ───────────────────────────────────────────────────────────

print("=" * 65)
print("📊 OVERALL EVALUATION")
print("=" * 65)

cm = confusion_matrix(y_true, y_pred)
tn, fp, fn, tp = cm.ravel()
print(f"\n  True Negatives  (correctly normal):   {tn:>6}")
print(f"  False Positives (false alarms):        {fp:>6}")
print(f"  False Negatives (missed anomalies):    {fn:>6}")
print(f"  True Positives  (caught anomalies):    {tp:>6}")
print("\nClassification Report:\n")
print(classification_report(y_true, y_pred, target_names=["Normal", "Anomaly"]))

try:
    auc = roc_auc_score(y_true, y_score)
    print(f"ROC-AUC Score: {auc:.4f}  (1.0=perfect, 0.5=random, aim >0.85)\n")
except Exception:
    pass

# ── Per-device breakdown ──────────────────────────────────────────────────────

print("=" * 65)
print("📋 PER-DEVICE BREAKDOWN")
print("=" * 65)

print(f"\n  {'Device':<25} {'True':>5} {'Det':>5} {'TP':>4} {'FP':>4} {'FN':>4}  "
      f"{'Precision':>10}  {'Recall':>8}")
print("  " + "-" * 75)

for device in sorted(df_all["device_name"].unique()):
    d     = df_all[df_all["device_name"] == device]
    n_true = d["is_true_anomaly"].sum()
    n_det  = d["model_predicted"].sum()
    tp_d   = ((d["is_true_anomaly"] == 1) & (d["model_predicted"] == 1)).sum()
    fp_d   = ((d["is_true_anomaly"] == 0) & (d["model_predicted"] == 1)).sum()
    fn_d   = ((d["is_true_anomaly"] == 1) & (d["model_predicted"] == 0)).sum()
    prec   = tp_d / max(tp_d + fp_d, 1)
    rec    = tp_d / max(tp_d + fn_d, 1)
    print(f"  {device:<25} {n_true:>5} {n_det:>5} {tp_d:>4} {fp_d:>4} {fn_d:>4}  "
          f"{prec:>10.2f}  {rec:>8.2f}")

# ── Missed anomalies ──────────────────────────────────────────────────────────

print("\n" + "=" * 65)
print("🔍 MISSED ANOMALIES (false negatives)")
print("=" * 65)

missed = df_all[(df_all["is_true_anomaly"] == 1) & (df_all["model_predicted"] == 0)]

if missed.empty:
    print("\n  ✅ No missed anomalies!\n")
else:
    print(f"\n  {len(missed)} anomalies the model failed to catch:\n")
    print(f"  {'Device':<25} {'Type':<20} {'Avg W':>7} {'Act Min':>8} {'Score':>9}")
    print("  " + "-" * 75)
    for _, row in missed.sort_values("anomaly_score").iterrows():
        print(f"  {row['device_name']:<25} "
              f"{str(row['ground_truth_anomaly']):<20} "
              f"{row['avg_power_W']:>7.1f} "
              f"{row['active_minutes']:>8} "
              f"{row['anomaly_score']:>9.5f}")

# ── Detection rate by anomaly type (pandas deprecation fix) ───────────────────

print("\n" + "=" * 65)
print("📊 ANOMALY TYPE DETECTION RATE")
print("=" * 65 + "\n")

anomaly_df = df_all[df_all["is_true_anomaly"] == 1].copy()

type_summary = (
    anomaly_df
    .groupby("ground_truth_anomaly")["model_predicted"]
    .agg(
        total="count",
        caught="sum"
    )
    .reset_index()
)
type_summary["missed"] = type_summary["total"] - type_summary["caught"]
type_summary["recall"] = type_summary["caught"] / type_summary["total"]

print(f"  {'Anomaly Type':<22} {'Total':>6} {'Caught':>7} {'Missed':>7} {'Recall':>8}")
print("  " + "-" * 55)
for _, row in type_summary.iterrows():
    bar = "█" * int(row["recall"] * 10)
    print(f"  {row['ground_truth_anomaly']:<22} "
          f"{int(row['total']):>6} "
          f"{int(row['caught']):>7} "
          f"{int(row['missed']):>7} "
          f"{row['recall']:>7.0%}  {bar}")

# ── Alerts collection summary ─────────────────────────────────────────────────

alert_count = alerts_col.count_documents({})
if alert_count > 0:
    print(f"\n\n📁 anomaly_alerts collection: {alert_count} total alerts stored")
    latest = alerts_col.find_one(sort=[("scored_at", -1)])
    if latest:
        print(f"   Latest alert: {latest['device_name']} at {latest['interval_start']}")