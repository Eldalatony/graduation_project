"""
reset_db.py
-----------
Wipes the analytics-owned collections so the adaptive pipeline re-runs from
scratch: alerts, checkpoints, and the per-device models/state.

Never touches `appliance_data` — that is the input from the backend ETL (and
the synthetic seed) and must not be deleted here. To regenerate the test
dataset too, run seed_synthetic.py (which wipes appliance_data itself).
"""
import os
import sys

# Make the sibling modules in src/ importable when run from src/scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import db

db["anomaly_alerts"].drop()
db["infer_checkpoint"].drop()
db["device_models"].drop()
print("✅ Cleared anomaly_alerts, infer_checkpoint, and device_models")
print("   (appliance_data left intact — devices will re-learn from it)")
