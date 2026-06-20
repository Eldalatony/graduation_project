"""
train.py
--------
Manual training helper for the adaptive system.

Normally you never run this — the background scheduler (app.py → infer.run_inference)
auto-trains each device the moment it reaches READY. This script is for testing:
it reports every device's progress and trains the ones that qualify right now.

  python train.py            # train only devices that meet the readiness gate
  python train.py --force    # train every device regardless (testing shortcut)

Training is unsupervised (Isolation Forest); any ground-truth labels in the data
are ignored here and used only by evaluate.py to measure accuracy.
"""
import os
import sys
import pandas as pd

# Make the sibling modules in src/ importable when run from src/scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import data_col, READY_MIN_RECORDS, READY_MIN_SPAN_DAYS
from model_manager import compute_progress, is_ready, train_device

force = "--force" in sys.argv

print(f"Readiness gate: ≥{READY_MIN_RECORDS} records AND ≥{READY_MIN_SPAN_DAYS}d span\n")

devices = data_col.distinct("device_name")
if not devices:
    print("❌ No data in appliance_data. Run seed_synthetic.py or let the ETL run.")
    sys.exit()

for device in sorted(devices):
    records = list(data_col.find({"device_name": device}, {"_id": 0}))
    df      = pd.DataFrame(records)
    prog    = compute_progress(df)
    ready, reasons = is_ready(prog)

    print(f"• {device:<20} {prog['n_records']:>4} records | "
          f"{prog['span_days']:>5.1f}d | active {prog['active_fraction']*100:>4.0f}%", end="  ")

    if ready or force:
        train_device(device, df)
        print("→ TRAINED ✅" + ("  (forced)" if force and not ready else ""))
    else:
        print(f"→ learning ({'; '.join(reasons)})")

print("\nDone. Run infer.py to score, or evaluate.py to measure accuracy.")
