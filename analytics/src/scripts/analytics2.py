"""
analytics2.py
-------------
Standalone CLI that prints daily/weekly/monthly/peak/per-device aggregations
straight from MongoDB. A quick console snapshot — the same numbers the API
serves over HTTP. Run: python src/scripts/analytics2.py
"""

import os
import sys

# Make the sibling modules in src/ importable when run from src/scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import db, data_col as collection


# =========================
# 1. DAILY AGGREGATION
# =========================
print("\n📅 Daily Energy Consumption:\n")

daily_pipeline = [
    {
        "$group": {
            "_id": {
                "$dateToString": {
                    "format": "%Y-%m-%d",
                    "date": {"$dateFromString": {"dateString": "$interval_start"}}
                }
            },
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"}
        }
    },
    {"$sort": {"_id": 1}}
]

for r in collection.aggregate(daily_pipeline):
    print(f"  {r['_id']}  →  {r['total_energy_kWh']:.4f} kWh  |  {r['total_cost_EGP']:.4f} EGP")


# =========================
# 2. WEEKLY AGGREGATION
# =========================
print("\n📆 Weekly Energy Consumption:\n")

weekly_pipeline = [
    {
        "$group": {
            "_id": {
                "year": {"$isoWeekYear": {"$dateFromString": {"dateString": "$interval_start"}}},
                "week": {"$isoWeek":     {"$dateFromString": {"dateString": "$interval_start"}}}
            },
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"}
        }
    },
    {"$sort": {"_id.year": 1, "_id.week": 1}}
]

for r in collection.aggregate(weekly_pipeline):
    print(f"  Year {r['_id']['year']} Week {r['_id']['week']:02d}  →  "
          f"{r['total_energy_kWh']:.4f} kWh  |  {r['total_cost_EGP']:.4f} EGP")


# =========================
# 3. MONTHLY AGGREGATION
# =========================
print("\n🗓️  Monthly Energy Consumption:\n")

monthly_pipeline = [
    {
        "$group": {
            "_id": {
                "year":  {"$year":  {"$dateFromString": {"dateString": "$interval_start"}}},
                "month": {"$month": {"$dateFromString": {"dateString": "$interval_start"}}}
            },
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"}
        }
    },
    {"$sort": {"_id.year": 1, "_id.month": 1}}
]

for r in collection.aggregate(monthly_pipeline):
    print(f"  {r['_id']['year']}-{r['_id']['month']:02d}  →  "
          f"{r['total_energy_kWh']:.4f} kWh  |  {r['total_cost_EGP']:.4f} EGP")


# =========================
# 4. PEAK USAGE HOURS
# =========================
print("\n⚡ Peak Usage Hours (top 5 by total energy):\n")

peak_pipeline = [
    {
        "$group": {
            "_id": {
                "$hour": {"$dateFromString": {"dateString": "$interval_start"}}
            },
            "total_energy_kWh": {"$sum": "$total_energy_kWh"}
        }
    },
    {"$sort": {"total_energy_kWh": -1}},
    {"$limit": 5}
]

for r in collection.aggregate(peak_pipeline):
    print(f"  Hour {r['_id']:02d}:00  →  {r['total_energy_kWh']:.3f} kWh")


# =========================
# 5. ENERGY & COST PER APPLIANCE
# =========================
print("\n💡 Energy & Cost per Appliance:\n")

cost_pipeline = [
    {
        "$group": {
            "_id":              "$device_name",
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
            "avg_power_W":      {"$avg": "$avg_power_W"}
        }
    },
    {"$sort": {"total_cost_EGP": -1}}
]

for r in collection.aggregate(cost_pipeline):
    print(
        f"  {r['_id']:<25} "
        f"Energy: {r['total_energy_kWh']:>8.2f} kWh  |  "
        f"Cost: {r['total_cost_EGP']:>8.2f} EGP  |  "
        f"Avg Power: {r['avg_power_W']:>6.1f} W"
    )


# =========================
# 6. ANOMALY SUMMARY (ground truth labels)
# =========================
print("\n🚨 Injected Anomaly Summary (ground truth):\n")

anomaly_pipeline = [
    {"$match": {"anomaly": {"$ne": None}}},
    {
        "$group": {
            "_id": {
                "device": "$device_name",
                "type":   "$anomaly"
            },
            "count": {"$sum": 1}
        }
    },
    {"$sort": {"_id.device": 1, "_id.type": 1}}
]

rows = list(collection.aggregate(anomaly_pipeline))
if rows:
    for r in rows:
        print(f"  {r['_id']['device']:<25} | {r['_id']['type']:<20} | count: {r['count']}")
else:
    print("  (no ground-truth anomaly labels found — normal for real data)")


# =========================
# 7. ALERTS SUMMARY
# =========================
alerts_col = db["anomaly_alerts"]
alert_count = alerts_col.count_documents({})

if alert_count > 0:
    print(f"\n\n📊 Anomaly Alerts Summary ({alert_count} total):\n")

    alerts_by_device_pipeline = [
        {
            "$group": {
                "_id":   "$device_name",
                "count": {"$sum": 1},
                "avg_anomaly_score": {"$avg": "$anomaly_score"}
            }
        },
        {"$sort": {"count": -1}}
    ]

    for r in alerts_col.aggregate(alerts_by_device_pipeline):
        print(f"  {r['_id']:<25} | alerts: {r['count']:>3} | "
              f"avg score: {r['avg_anomaly_score']:.5f}")