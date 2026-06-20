"""
seed_synthetic.py
-----------------
Generates realistic HOURLY appliance data for the system's real devices
(Kitchen, Laundry, Climate) so the adaptive models can reach READY instantly
during testing — instead of waiting two real weeks for data to accumulate.

This is a TEST FIXTURE, not a bypass. It produces data in exactly the same
shape the backend ETL writes, with a realistic daily/weekly rhythm per device,
plus a small number of clearly-labeled anomalies. The labels are used ONLY to
measure accuracy (evaluate.py) — training stays fully unsupervised, exactly as
it will in production.

Run from inside the container:
  docker compose exec analytics python src/scripts/seed_synthetic.py
"""
import os
import sys
import random
from datetime import datetime, timezone, timedelta

# Make the sibling modules in src/ importable when run from src/scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import data_col, alerts_col, checkpoint_col, device_models_col

random.seed(42)

COST_PER_KWH_EGP = 1.5            # matches the backend ETL tariff
N_DAYS  = int(os.environ.get("SEED_DAYS", "21"))   # > READY_MIN_SPAN_DAYS (14)
GATEWAY = "gateway_1"

DEVICES = [
    {"node_key": "node_1", "device_type": "kitchen", "device_name": "Kitchen", "max_w": 2000},
    {"node_key": "node_2", "device_type": "laundry", "device_name": "Laundry", "max_w": 2500},
    {"node_key": "node_3", "device_type": "climate", "device_name": "Climate", "max_w": 2800},
]

ANOMALY_TYPES = ["power_spike", "excessive_runtime", "abnormal_idle", "stuck_on"]


# ── Normal behaviour profiles (avg_power, active_min, max_power) ────────────────
def normal_reading(device_name, dt):
    hour = dt.hour
    weekend = dt.weekday() >= 5

    if device_name == "Kitchen":
        # Cooking appliances: idle most of the day, spikes at meal times.
        if hour in (7, 8, 12, 13, 18, 19, 20):
            avg    = random.uniform(150, 900) * (1.25 if weekend else 1.0)
            active = random.randint(15, 45)
            maxp   = avg + random.uniform(200, 1100)
        else:
            avg    = random.uniform(2, 30)
            active = random.randint(0, 8)
            maxp   = avg + random.uniform(5, 60)

    elif device_name == "Laundry":
        # Fridge/freezer cycles every hour; washer/dryer bursts now and then.
        avg    = random.uniform(50, 110)
        active = random.randint(25, 50)
        maxp   = avg + random.uniform(40, 200)
        if 9 <= hour <= 21 and random.random() < (0.10 if weekend else 0.04):
            avg    = random.uniform(800, 2000)
            active = random.randint(30, 60)
            maxp   = avg + random.uniform(100, 500)

    else:  # Climate — water heater + AC
        if hour in (6, 7, 19, 20, 21):                       # water-heater windows
            avg    = random.uniform(800, 2000)
            active = random.randint(10, 40)
            maxp   = avg + random.uniform(100, 800)
        elif 13 <= hour <= 17 and (weekend or random.random() < 0.5):  # afternoon AC
            avg    = random.uniform(300, 1200)
            active = random.randint(25, 55)
            maxp   = avg + random.uniform(100, 600)
        else:
            avg    = random.uniform(8, 60)
            active = random.randint(0, 15)
            maxp   = avg + random.uniform(10, 80)

    return avg, active, maxp


def apply_anomaly(atype, avg, active, maxp, max_w):
    if atype == "power_spike":
        avg    = random.uniform(max_w * 1.4, max_w * 2.0)
        maxp   = avg + random.uniform(10, 60)
    elif atype == "excessive_runtime":
        active = 60                                  # runs the whole hour
    elif atype == "abnormal_idle":
        avg, active, maxp = 0.0, 0, 0.0              # dead when it should run
    elif atype == "stuck_on":
        avg    = random.uniform(max_w * 0.85, max_w)
        active = 60
        maxp   = avg + random.uniform(0, 20)
    return avg, active, maxp


# ── Generate ────────────────────────────────────────────────────────────────────
def generate():
    end   = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=N_DAYS)

    intervals = []
    t = start
    while t < end:
        intervals.append(t)
        t += timedelta(hours=1)

    # Sparse anomaly schedule (~1.5% of all slots), spread across devices/time.
    slots = [(i, d["device_name"]) for i in range(len(intervals)) for d in DEVICES]
    n_anom = max(1, int(len(slots) * 0.015))
    schedule = {s: random.choice(ANOMALY_TYPES) for s in random.sample(slots, n_anom)}
    print(f"Scheduling {n_anom} anomalies across {len(DEVICES)} devices × {len(intervals)} hours")

    docs = []
    for i, dt in enumerate(intervals):
        for dev in DEVICES:
            avg, active, maxp = normal_reading(dev["device_name"], dt)
            label = schedule.get((i, dev["device_name"]))
            if label:
                avg, active, maxp = apply_anomaly(label, avg, active, maxp, dev["max_w"])

            active   = int(max(0, min(60, active)))
            avg      = round(max(0.0, avg), 1)
            maxp     = round(max(avg, maxp), 1)
            energy   = round(avg / 1000.0, 4)          # avg W over 1 hour → kWh
            cost     = round(energy * COST_PER_KWH_EGP, 4)

            docs.append({
                "gateway_id":       GATEWAY,
                "node_key":         dev["node_key"],
                "device_type":      dev["device_type"],
                "device_name":      dev["device_name"],
                "interval_start":   dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "interval_end":     (dt + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "avg_power_W":      avg,
                "max_power_W":      maxp,
                "min_power_W":      round(random.uniform(0, 5), 1),
                "total_energy_kWh": energy,
                "total_cost_EGP":   cost,
                "active_minutes":   active,
                "idle_minutes":     60 - active,
                "status_changes":   random.choice([0, 2, 4]),
                "anomaly":          label,            # ground truth (eval only)
                "created_at":       datetime.now(timezone.utc),
            })
    return docs


if __name__ == "__main__":
    print("⚠️  Wiping analytics collections for a clean test slate "
          "(appliance_data, anomaly_alerts, infer_checkpoint, device_models)…")
    data_col.drop()
    alerts_col.drop()
    checkpoint_col.drop()
    device_models_col.drop()

    docs = generate()
    print(f"Generated {len(docs)} hourly records over {N_DAYS} days. Inserting…")
    for i in range(0, len(docs), 1000):
        data_col.insert_many(docs[i:i + 1000])
    data_col.create_index([("device_name", 1), ("interval_start", 1)])
    print(f"✅ Inserted {len(docs)} records. Run infer.py to train + score.")
