"""
classify_backfill.py
--------------------
One-off (idempotent) backfill: assign an `anomaly_type` to every alert already
stored in `anomaly_alerts`, and persist each device's baseline into its
`device_models` doc so future inline classification has it ready.

Existing alerts were written before the classifier existed, so they only carry
the synthetic `ground_truth_anomaly` (often null). This re-labels them using the
exact same rule layer the live inference tick now uses. Safe to re-run.

Run inside the analytics container:
    docker exec shemms_analytics python /app/src/scripts/classify_backfill.py
"""

import os
import sys
import logging
import pandas as pd

# Make the sibling modules in src/ importable when run from src/scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import data_col, alerts_col, device_models_col
from classifier import compute_baseline, classify_anomaly, TYPE_LABELS
from model_manager import engineer_features

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("analytics.backfill")


def baseline_for(device_name: str, cache: dict) -> dict:
    """Compute (and cache + persist) a device's normal baseline."""
    if device_name in cache:
        return cache[device_name]

    records = list(data_col.find({"device_name": device_name}, {"_id": 0}))
    if records:
        df = engineer_features(pd.DataFrame(records))
        baseline = compute_baseline(df)
        # Persist so live inference can reuse it without recomputing.
        device_models_col.update_one(
            {"device_name": device_name},
            {"$set": {"baseline": baseline}},
        )
    else:
        baseline = {}
    cache[device_name] = baseline
    return baseline


def run_backfill() -> dict:
    cache: dict = {}
    counts: dict = {}
    updated = 0

    for a in alerts_col.find({}):
        device = a.get("device_name", "")
        baseline = baseline_for(device, cache)

        runtime_ratio = a.get("runtime_ratio")
        if runtime_ratio is None:
            runtime_ratio = a.get("active_minutes", 0) / 60.0

        atype = classify_anomaly(
            a.get("avg_power_W", 0.0), a.get("max_power_W", 0.0),
            a.get("active_minutes", 0), runtime_ratio, baseline,
        )
        alerts_col.update_one({"_id": a["_id"]}, {"$set": {"anomaly_type": atype}})
        counts[atype] = counts.get(atype, 0) + 1
        updated += 1

    log.info(f"Backfilled {updated} alerts across {len(cache)} devices.")
    for atype, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        log.info(f"  {TYPE_LABELS.get(atype, atype):<20} {n}")
    return {"updated": updated, "by_type": counts}


if __name__ == "__main__":
    result = run_backfill()
    print(f"\nResult: {result}\n")
