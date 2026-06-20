"""
forecaster.py
-------------
Per-device energy forecaster — the time-AWARE counterpart to the Isolation
Forest in model_manager.py.

The anomaly model is deliberately time-BLIND (it excludes hour-of-day so a
0-watt night hour looks like a normal idle hour). Forecasting needs the exact
opposite: it lives on daily/weekly seasonality. So this is a *second* model
reading the same appliance_data, with a different feature set and a different
target — predict future total_energy_kWh — not a replacement for the detector.

Two layers, so it degrades gracefully (mirrors model + rule baseline on the
anomaly side):

  1. Profile baseline  — mean kWh per (hour_of_day, day_of_week), a 24x7 table.
                         Robust, interpretable, always available, used as the
                         cold-start answer and to clamp the regression.
  2. Linear Regression — Ridge on cyclical + lag features. This is the model;
                         Ridge is linear regression with L2 regularisation
                         (swap in LinearRegression for the textbook variant).

State lives in the same `device_models` doc as the anomaly model, under
`forecast_*` keys, so it survives rebuilds and reuses the LEARNING→READY gate
(training is only ever called once a device is READY — see infer.py).
"""

import math
import logging
import pandas as pd
from datetime import datetime, timedelta, timezone

from sklearn.linear_model import Ridge

from shared import device_models_col, serialize_model, deserialize_model

log = logging.getLogger("analytics.forecaster")

# Feature order — must stay in sync between training and walk-forward predict.
FORECAST_FEATURES = [
    "hour_sin", "hour_cos", "dow_sin", "dow_cos", "is_weekend",
    "lag_24h", "lag_168h",
]

DEFAULT_TARIFF_EGP_PER_KWH = 1.5  # matches the backend ETL / seed tariff
MIN_TRAIN_ROWS = 168              # need ≥ one full week after the 168h lag


# ── Features ──────────────────────────────────────────────────────────────────
def _calendar_feats(ts: pd.Timestamp) -> dict:
    """Cyclical calendar features for one timestamp. Single source of truth so
    training (vectorised) and predict (scalar walk-forward) can never drift."""
    return {
        "hour_sin":   math.sin(2 * math.pi * ts.hour / 24),
        "hour_cos":   math.cos(2 * math.pi * ts.hour / 24),
        "dow_sin":    math.sin(2 * math.pi * ts.dayofweek / 7),
        "dow_cos":    math.cos(2 * math.pi * ts.dayofweek / 7),
        "is_weekend": 1.0 if ts.dayofweek >= 5 else 0.0,
    }


def forecast_features(df: pd.DataFrame) -> pd.DataFrame:
    """Time-aware features for training. Assumes one device's contiguous hourly
    rows (shift-based lags); gaps just make a few lag rows approximate, which the
    dropna in train_forecaster discards."""
    df = df.sort_values("interval_start").copy()
    times = pd.to_datetime(df["interval_start"], utc=True)
    cal = pd.DataFrame([_calendar_feats(ts) for ts in times], index=df.index)
    df = pd.concat([df, cal], axis=1)
    df["lag_24h"]  = df["total_energy_kWh"].shift(24)    # same hour yesterday
    df["lag_168h"] = df["total_energy_kWh"].shift(168)   # same hour last week
    return df


def build_profile(df: pd.DataFrame) -> dict:
    """24x7 mean-kWh table keyed "hour:dow" — the robust fallback layer."""
    times = pd.to_datetime(df["interval_start"], utc=True)
    g = (df.assign(_h=times.dt.hour, _d=times.dt.dayofweek)
           .groupby(["_h", "_d"])["total_energy_kWh"].mean())
    return {f"{int(h)}:{int(d)}": float(v) for (h, d), v in g.items()}


def effective_tariff(df: pd.DataFrame) -> float:
    """Derive EGP/kWh from the device's own data instead of hardcoding, so a
    device on a different rate still projects correctly."""
    energy = float(df["total_energy_kWh"].sum())
    cost   = float(df.get("total_cost_EGP", pd.Series(dtype=float)).sum())
    if energy > 0 and cost > 0:
        return cost / energy
    return DEFAULT_TARIFF_EGP_PER_KWH


# ── Training ──────────────────────────────────────────────────────────────────
def train_forecaster(device_name: str, device_df: pd.DataFrame) -> dict:
    """Fit Ridge on time + lag features and store model + profile + tariff in the
    device's existing device_models doc. Called from infer.py right where the
    anomaly model trains/retrains, so it reuses the READY gate."""
    profile = build_profile(device_df)
    tariff  = effective_tariff(device_df)

    feat = forecast_features(device_df).dropna(subset=["lag_24h", "lag_168h"])
    blob = None
    n_train = len(feat)
    if n_train >= MIN_TRAIN_ROWS:
        model = Ridge(alpha=1.0)
        model.fit(feat[FORECAST_FEATURES], feat["total_energy_kWh"])
        blob = serialize_model(model)

    now = datetime.now(timezone.utc).isoformat()
    device_models_col.update_one(
        {"device_name": device_name},
        {"$set": {
            "forecast_blob":       blob,                # None → profile-only
            "forecast_profile":    profile,
            "forecast_features":   FORECAST_FEATURES,
            "forecast_tariff":     round(tariff, 6),
            "forecast_trained_at": now,
            "forecast_n_train":    n_train,
        }},
        upsert=True,
    )
    log.info(f"📈 Forecaster for '{device_name}': "
             f"{'ridge' if blob else 'profile-only'} on {n_train} rows")
    return {"device_name": device_name, "method": "ridge" if blob else "profile",
            "n_train": n_train}


def load_forecaster(device_name: str):
    """Returns (model_or_None, profile_dict, tariff, feature_order)."""
    doc = device_models_col.find_one({"device_name": device_name}) or {}
    blob    = doc.get("forecast_blob")
    model   = deserialize_model(blob) if blob else None
    profile = doc.get("forecast_profile") or {}
    tariff  = doc.get("forecast_tariff", DEFAULT_TARIFF_EGP_PER_KWH)
    feats   = doc.get("forecast_features", FORECAST_FEATURES)
    return model, profile, tariff, feats


# ── Prediction (walk-forward) ─────────────────────────────────────────────────
def _profile_mean(profile: dict) -> float:
    return sum(profile.values()) / len(profile) if profile else 0.0


def forecast_device(device_name: str, device_df: pd.DataFrame,
                    horizon_hours: int) -> dict:
    """Forecast hourly kWh/cost for the next `horizon_hours` after the device's
    last interval. Uses Ridge when trained, else the profile. Falls back to a
    profile built on the fly from device_df so it still works before training.
    Predictions feed back in as lags for genuine multi-step forecasting, and are
    clamped to the device's historical range so a bad extrapolation can't blow
    up the bill."""
    if device_df is None or device_df.empty:
        return {"device_name": device_name, "method": "none", "points": [],
                "total_predicted_kWh": 0.0, "total_predicted_cost_EGP": 0.0}

    df = device_df.sort_values("interval_start").copy()
    model, profile, tariff, feats = load_forecaster(device_name)
    if not profile:                       # never trained — derive on the fly
        profile = build_profile(df)
        tariff  = effective_tariff(df)

    times = pd.to_datetime(df["interval_start"], utc=True)
    series = dict(zip(times, df["total_energy_kWh"].astype(float)))
    last      = times.max()
    max_kwh   = float(df["total_energy_kWh"].max())
    fallback  = _profile_mean(profile)

    def profile_val(ts):
        return profile.get(f"{ts.hour}:{ts.dayofweek}", fallback)

    def lag(ts, hours):
        key = ts - timedelta(hours=hours)
        return series.get(key, profile_val(key))

    method = "ridge" if model is not None else "profile"
    points = []
    for h in range(1, horizon_hours + 1):
        ts = last + timedelta(hours=h)
        if model is not None:
            row = _calendar_feats(ts)
            row["lag_24h"]  = lag(ts, 24)
            row["lag_168h"] = lag(ts, 168)
            X = pd.DataFrame([[row[f] for f in feats]], columns=feats)
            pred = float(model.predict(X)[0])
            pred = min(max(pred, 0.0), max(max_kwh * 1.5, fallback))  # clamp
        else:
            pred = profile_val(ts)
        series[ts] = pred
        points.append({
            "interval_start":     ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "predicted_kWh":      round(pred, 4),
            "predicted_cost_EGP": round(pred * tariff, 4),
        })

    return {
        "device_name":               device_name,
        "method":                    method,
        "tariff_EGP_per_kWh":        round(tariff, 4),
        "horizon_hours":             horizon_hours,
        "points":                    points,
        "total_predicted_kWh":       round(sum(p["predicted_kWh"] for p in points), 4),
        "total_predicted_cost_EGP":  round(sum(p["predicted_cost_EGP"] for p in points), 2),
    }
