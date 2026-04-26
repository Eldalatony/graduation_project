import pymongo
from datetime import datetime, timedelta
import random

client = pymongo.MongoClient(
    "mongodb+srv://admin:admin123@cluster0.nvratez.mongodb.net/smart_home?authSource=admin"
)

db = client["smart_home"]
collection = db["appliance_data"]

start_date = datetime(2026, 1, 1, 0, 0, 0)
end_date = start_date + timedelta(days=60)
current_time = start_date

appliances = [
    {"node_key": "node_1", "device_type": "refrigerator",    "device_name": "Main Refrigerator", "min_w": 0,   "max_w": 200,  "avg_w_range": (80, 120),  "active_range": (15, 25)},
    {"node_key": "node_2", "device_type": "deep_freezer",    "device_name": "Deep Freezer",      "min_w": 0,   "max_w": 250,  "avg_w_range": (100, 150), "active_range": (18, 28)},
    {"node_key": "node_3", "device_type": "water_dispenser", "device_name": "Water Dispenser",   "min_w": 0,   "max_w": 600,  "avg_w_range": (10, 60),   "active_range": (2, 10)},
    {"node_key": "node_4", "device_type": "microwave",       "device_name": "Microwave",         "min_w": 0,   "max_w": 1200, "avg_w_range": (2, 5),     "active_range": (0, 3)},
    {"node_key": "node_5", "device_type": "beverage_fridge", "device_name": "Beverage Fridge",   "min_w": 0,   "max_w": 150,  "avg_w_range": (50, 90),   "active_range": (12, 20)},
]

COST_PER_KWH_EGP = 1.65

# ---------------------------------------------------------------------------
# Anomaly registry
# Each entry defines ONE anomaly event:  which device, which interval index,
# and which fault type to inject.
# We pre-generate this ONCE so it is stable and sparse (≈ 0.5 % of records).
# ---------------------------------------------------------------------------
ANOMALY_TYPES = ["power_spike", "excessive_runtime", "abnormal_idle", "stuck_on"]

def build_anomaly_schedule(total_intervals, num_anomalies=40):
    """
    Returns a dict: (interval_index, node_key) -> anomaly_type
    Anomalies are spread randomly across all devices and all time slots.
    """
    schedule = {}
    all_slots = [
        (i, app["node_key"])
        for i in range(total_intervals)
        for app in appliances
    ]
    chosen = random.sample(all_slots, min(num_anomalies, len(all_slots)))
    for slot in chosen:
        schedule[slot] = random.choice(ANOMALY_TYPES)
    return schedule


def apply_anomaly(anomaly_type, app, avg_power, active_mins, max_p, min_p):
    """
    Overwrite sensor fields to simulate a real fault.
    Returns (avg_power, active_mins, max_p, min_p, anomaly_label)
    """
    if anomaly_type == "power_spike":
        # Sudden surge well above the device's rated maximum
        spike = random.uniform(app["max_w"] * 1.4, app["max_w"] * 2.0)
        avg_power = round(spike, 1)
        max_p     = round(spike + random.uniform(10, 50), 1)
        # active time looks normal — the spike itself is the fault
        active_mins = random.randint(
            max(1, app["active_range"][0]),
            max(5, app["active_range"][1])
        )

    elif anomaly_type == "excessive_runtime":
        # Device runs almost the entire 30-minute window
        active_mins = random.randint(28, 30)
        # Power is within normal range — it's the duration that is wrong
        avg_power = random.uniform(app["avg_w_range"][0], app["avg_w_range"][1])
        max_p     = random.uniform(avg_power + 5, app["max_w"])

    elif anomaly_type == "abnormal_idle":
        # Device that should be running goes completely silent
        avg_power   = 0.0
        max_p       = 0.0
        min_p       = 0.0
        active_mins = 0

    elif anomaly_type == "stuck_on":
        # Device locked in a sustained high-draw state (e.g. stuck relay)
        stuck_power = random.uniform(app["max_w"] * 0.85, app["max_w"])
        avg_power   = round(stuck_power, 1)
        max_p       = round(stuck_power + random.uniform(0, 10), 1)
        active_mins = 30          # fully stuck — no idle time

    return avg_power, active_mins, max_p, min_p, anomaly_type


def generate_documents():
    global current_time

    # Total 30-minute intervals in 60 days
    total_intervals = 60 * 24 * 2   # 2880

    anomaly_schedule = build_anomaly_schedule(total_intervals, num_anomalies=40)
    print(f"Scheduled {len(anomaly_schedule)} anomaly events across all devices.")

    documents      = []
    interval_index = 0
    current_time   = start_date

    print("Generating 60 days of data...")

    while current_time < end_date:
        interval_end = current_time + timedelta(minutes=30)

        for app in appliances:
            # --- Normal baseline values ---
            avg_power   = random.uniform(app["avg_w_range"][0], app["avg_w_range"][1])
            active_mins = random.randint(app["active_range"][0], app["active_range"][1])
            max_p       = random.uniform(avg_power + 10, app["max_w"])
            min_p       = random.uniform(app["min_w"], app["min_w"] + 5)

            # --- Microwave: two legitimate operating states (NOT an anomaly) ---
            if app["device_type"] == "microwave":
                if random.random() < 0.15:          # ~15 % chance device is actually in use
                    avg_power   = random.uniform(600, 1100)
                    active_mins = random.randint(1, 5)
                    max_p       = random.uniform(avg_power, 1200)
                else:
                    avg_power   = random.uniform(0, 5)   # standby / idle
                    active_mins = 0
                    max_p       = random.uniform(5, 15)

            # --- Inject anomaly if this slot is scheduled ---
            anomaly_label = None
            key = (interval_index, app["node_key"])
            if key in anomaly_schedule:
                anomaly_type = anomaly_schedule[key]
                avg_power, active_mins, max_p, min_p, anomaly_label = apply_anomaly(
                    anomaly_type, app, avg_power, active_mins, max_p, min_p
                )

            idle_mins  = max(0, 30 - active_mins)
            energy_kwh = (avg_power * 0.5) / 1000
            cost_egp   = energy_kwh * COST_PER_KWH_EGP

            doc = {
                "gateway_id":        "gateway_1",
                "node_key":          app["node_key"],
                "device_type":       app["device_type"],
                "device_name":       app["device_name"],
                "interval_start":    current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "interval_end":      interval_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "avg_power_W":       round(avg_power, 1),
                "max_power_W":       round(max_p, 1),
                "min_power_W":       round(min_p, 1),
                "total_energy_kWh":  round(energy_kwh, 4),
                "total_cost_EGP":    round(cost_egp, 4),
                "active_minutes":    active_mins,
                "idle_minutes":      idle_mins,
                "status_changes":    random.choice([0, 2, 4]),
                # Ground-truth label — None means normal operation
                "anomaly":           anomaly_label,
            }

            documents.append(doc)

        current_time = interval_end
        interval_index += 1

    return documents


# ── Insert ──────────────────────────────────────────────────────────────────
data_to_insert = generate_documents()

print(f"Generated {len(data_to_insert)} records.")
print("Injecting into MongoDB...")

for i in range(0, len(data_to_insert), 1000):
    batch = data_to_insert[i:i + 1000]
    collection.insert_many(batch)
    print(f"Inserted {i + len(batch)} / {len(data_to_insert)} records...")

print("✅ Success! Database is fully populated.")