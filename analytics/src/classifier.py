"""
classifier.py
-------------
A rule-based *labelling* layer that sits on top of the unsupervised anomaly
detector.

The Isolation Forest only answers "is this hour weird?" — it never says *what
kind* of weird. This module looks at a flagged interval's features and assigns a
human-readable anomaly type, so alerts read "Power spike" / "Stuck on" instead of
"Unclassified".

It compares each anomaly against the device's OWN normal baseline (percentiles
of its history), so the same rule works whether the device is a 50 W light or a
2 kW kettle. No labels, no training — pure interpretation of what the detector
already flagged.

Anomaly types produced:
  power_spike       brief burst with a peak far above the device's normal max
  stuck_on          near-continuous runtime, usually at elevated power
  excessive_runtime runs much longer than usual at otherwise-normal power
  abnormal_idle     a normally-active device draws ~0 W (the detector's blind
                    spot — labelled here for completeness when it is flagged)
  high_power_draw   average power well above normal during partial runtime
  unusual_pattern   flagged as anomalous but matches none of the above
"""

import numpy as np
import pandas as pd

from shared import INTERVAL_MINUTES

TYPE_LABELS = {
    "power_spike":       "Power spike",
    "stuck_on":          "Stuck on",
    "excessive_runtime": "Excessive runtime",
    "abnormal_idle":     "Abnormal idle",
    "high_power_draw":   "High power draw",
    "unusual_pattern":   "Unusual pattern",
}

def compute_baseline(device_df: pd.DataFrame) -> dict:
    """
    Summarise a device's normal behaviour as a handful of percentiles.

    The history is ~98% normal (contamination ≈ 2%), so percentiles taken over
    the whole series describe "normal" well enough to compare a single anomaly
    against. Power stats use only active intervals so an idle-heavy device does
    not drag its "normal power" down to zero.
    """
    df = device_df.copy()
    if "runtime_ratio" not in df.columns:
        df["runtime_ratio"] = df["active_minutes"] / float(INTERVAL_MINUTES)

    active = df[df["active_minutes"] > 0]

    def pct(series, q, default=0.0):
        s = pd.to_numeric(series, errors="coerce").dropna()
        return float(np.percentile(s, q)) if len(s) else default

    return {
        "avg_power_active_p50": pct(active["avg_power_W"], 50),
        "avg_power_active_p95": pct(active["avg_power_W"], 95),
        "max_power_p95":        pct(active["max_power_W"], 95),
        "active_minutes_p50":   pct(active["active_minutes"], 50),
        "active_minutes_p95":   pct(active["active_minutes"], 95),
        "runtime_ratio_p95":    pct(df["runtime_ratio"], 95),
        "active_fraction":      float((df["active_minutes"] > 0).mean()) if len(df) else 0.0,
    }

def classify_anomaly(avg_power_W: float, max_power_W: float,
                     active_minutes: float, runtime_ratio: float,
                     baseline: dict | None = None) -> str:
    """
    Map one flagged interval to an anomaly type. Rules are checked in priority
    order; the first match wins. Falls back to absolute heuristics when no
    baseline is available so it never crashes on a cold device.
    """
    b = baseline or {}
    avg_p50 = b.get("avg_power_active_p50") or 0.0
    avg_p95 = b.get("avg_power_active_p95") or 0.0
    max_p95 = b.get("max_power_p95") or 0.0
    act_p95 = b.get("active_minutes_p95") or 0.0
    typically_active = b.get("active_fraction", 1.0)

    avg = float(avg_power_W or 0.0)
    mx  = float(max_power_W or 0.0)
    act = float(active_minutes or 0.0)
    rr  = float(runtime_ratio or 0.0)

    if act == 0 or avg < 1.0:
        return "abnormal_idle" if typically_active >= 0.2 else "unusual_pattern"

    peaky = (max_p95 > 0 and mx > max_p95 * 1.4) or (mx > avg * 4 and mx > 300)

    if peaky and rr < 0.85:
        return "power_spike"

    if rr >= 0.85:
        elevated = (avg_p95 > 0 and avg > avg_p95) or (avg_p50 > 0 and avg > avg_p50 * 1.4)
        if elevated:
            return "stuck_on"
        if act_p95 > 0 and act > act_p95:
            return "excessive_runtime"
        return "stuck_on"

    if act_p95 > 0 and act > act_p95 * 1.2:
        return "excessive_runtime"

    if (avg_p95 > 0 and avg > avg_p95) or (avg_p50 > 0 and avg > avg_p50 * 1.6):
        return "high_power_draw"

    if peaky:
        return "power_spike"

    return "unusual_pattern"
