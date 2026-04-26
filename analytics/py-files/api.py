"""
api.py
------
Analytics API — Smart Home Energy Monitoring System
Phase 4 | All endpoints operational

Endpoints:
  GET /api/health
  GET /api/analytics/summary                   ← NEW: single call for dashboard home
  GET /api/analytics/:applianceId/daily
  GET /api/analytics/:applianceId/weekly
  GET /api/analytics/:applianceId/monthly
  GET /api/analytics/:applianceId/peak-hours
  GET /api/analytics/total/cost
  GET /api/analytics/anomalies
  GET /api/analytics/bill-estimate

Run:
  pip install flask flask-cors
  python api.py
  → http://localhost:5000
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import pymongo
from datetime import datetime, timezone
import io

# ── Config ────────────────────────────────────────────────────────────────────

MONGO_URI = "mongodb://admin:admin123@ac-smxdtmy-shard-00-00.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-01.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-02.nvratez.mongodb.net:27017/?ssl=true&replicaSet=atlas-12lqnf-shard-0&authSource=admin&appName=Cluster0"

# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

client     = pymongo.MongoClient(MONGO_URI)
db         = client["smart_home"]
data_col   = db["appliance_data"]
alerts_col = db["anomaly_alerts"]

# ── Response helpers ──────────────────────────────────────────────────────────

def ok(data):
    return jsonify({"status": "ok", "data": data})

def err(message, code=400):
    return jsonify({"status": "error", "message": message}), code

# ── Appliance filter resolver ─────────────────────────────────────────────────

def resolve_filter(appliance_id: str) -> dict:
    """
    Converts :applianceId to a MongoDB match filter.
      'all'       → {} (no filter, all devices)
      'node_1'    → match by node_key
      'Microwave' → case-insensitive match by device_name
    """
    if appliance_id.lower() == "all":
        return {}
    if data_col.find_one({"node_key": appliance_id}):
        return {"node_key": appliance_id}
    return {"device_name": {"$regex": f"^{appliance_id}$", "$options": "i"}}

# ── Silence favicon 404 ───────────────────────────────────────────────────────

@app.route("/favicon.ico")
def favicon():
    # Return a 1x1 transparent PNG so browsers don't spam 404 logs
    transparent_png = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        b'\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
        b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
        b'\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    return send_file(io.BytesIO(transparent_png), mimetype="image/png")


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# GET /api/health
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/health", methods=["GET"])
def health():
    try:
        db.command("ping")
        return ok({
            "database":  "connected",
            "records":   data_col.count_documents({}),
            "alerts":    alerts_col.count_documents({}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        return err(f"Database unreachable: {e}", 503)


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD SUMMARY  ← NEW
# GET /api/analytics/summary
# Returns everything the dashboard home screen needs in one request:
#   - grand totals (energy, cost)
#   - per-device cost share
#   - projected 30-day bill
#   - anomaly count + most recent alert
#   - top 3 peak hours
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/summary", methods=["GET"])
def summary():
    # Grand totals
    grand_agg = next(data_col.aggregate([
        {"$group": {
            "_id": None,
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
        }}
    ]), {"total_energy_kWh": 0, "total_cost_EGP": 0})

    # Per-device totals + cost share
    device_totals = list(data_col.aggregate([
        {"$group": {
            "_id":              "$device_name",
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
            "avg_power_W":      {"$avg": "$avg_power_W"},
            "record_count":     {"$sum": 1},
        }},
        {"$sort": {"total_cost_EGP": -1}}
    ]))

    grand_cost = grand_agg["total_cost_EGP"] or 1
    per_device = [
        {
            "device_name":        d["_id"],
            "total_energy_kWh":   round(d["total_energy_kWh"], 4),
            "total_cost_EGP":     round(d["total_cost_EGP"],   4),
            "avg_power_W":        round(d["avg_power_W"],       2),
            "share_of_total_pct": round(d["total_cost_EGP"] / grand_cost * 100, 1),
        }
        for d in device_totals
    ]

    # Projected 30-day bill from average daily cost
    daily_avg_agg = next(data_col.aggregate([
        {"$group": {
            "_id": {"$dateToString": {
                "format": "%Y-%m-%d",
                "date":   {"$dateFromString": {"dateString": "$interval_start"}}
            }},
            "day_cost": {"$sum": "$total_cost_EGP"},
        }},
        {"$group": {
            "_id": None,
            "avg_daily_cost": {"$avg": "$day_cost"},
            "total_days":     {"$sum": 1},
        }}
    ]), {"avg_daily_cost": 0, "total_days": 0})

    projected_bill = round(daily_avg_agg["avg_daily_cost"] * 30, 2)

    # Anomaly summary
    alert_count  = alerts_col.count_documents({})
    latest_alert = alerts_col.find_one(
        {}, {"_id": 0, "device_name": 1, "interval_start": 1,
             "avg_power_W": 1, "anomaly_score": 1, "ground_truth_anomaly": 1},
        sort=[("anomaly_score", 1)]   # most severe
    )
    alerts_by_device = list(alerts_col.aggregate([
        {"$group": {
            "_id":         "$device_name",
            "count":       {"$sum": 1},
            "worst_score": {"$min": "$anomaly_score"},
        }},
        {"$sort": {"count": -1}}
    ]))

    # Top 3 peak hours (all devices combined)
    peak = list(data_col.aggregate([
        {"$group": {
            "_id":              {"$hour": {"$dateFromString": {"dateString": "$interval_start"}}},
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
        }},
        {"$sort": {"total_energy_kWh": -1}},
        {"$limit": 3},
        {"$project": {
            "_id": 0,
            "hour":             "$_id",
            "total_energy_kWh": {"$round": ["$total_energy_kWh", 3]},
        }}
    ]))

    # Date range
    first = data_col.find_one(sort=[("interval_start",  1)])
    last  = data_col.find_one(sort=[("interval_start", -1)])

    return ok({
        "data_range": {
            "from": first["interval_start"] if first else None,
            "to":   last["interval_start"]  if last  else None,
            "days": daily_avg_agg["total_days"],
        },
        "totals": {
            "energy_kWh": round(grand_agg["total_energy_kWh"], 4),
            "cost_EGP":   round(grand_agg["total_cost_EGP"],   4),
        },
        "projected_monthly_bill_EGP": projected_bill,
        "per_device":   per_device,
        "anomalies": {
            "total_alerts":  alert_count,
            "by_device":     [
                {
                    "device_name": a["_id"],
                    "count":       a["count"],
                    "worst_score": round(a["worst_score"], 6),
                }
                for a in alerts_by_device
            ],
            "most_severe_alert": latest_alert,
        },
        "peak_hours": peak,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 1 — Daily consumption
# GET /api/analytics/:applianceId/daily
# Query params: ?from=YYYY-MM-DD  ?to=YYYY-MM-DD
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/<appliance_id>/daily", methods=["GET"])
def daily(appliance_id):
    match     = resolve_filter(appliance_id)
    date_from = request.args.get("from")
    date_to   = request.args.get("to")

    if date_from or date_to:
        match.setdefault("interval_start", {})
        if date_from:
            match["interval_start"]["$gte"] = f"{date_from}T00:00:00Z"
        if date_to:
            match["interval_start"]["$lte"] = f"{date_to}T23:59:59Z"

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "date":   {"$dateToString": {
                    "format": "%Y-%m-%d",
                    "date":   {"$dateFromString": {"dateString": "$interval_start"}}
                }},
                "device": "$device_name"
            },
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
            "avg_power_W":      {"$avg": "$avg_power_W"},
            "total_active_min": {"$sum": "$active_minutes"},
        }},
        {"$sort": {"_id.date": 1, "_id.device": 1}},
        {"$project": {
            "_id": 0,
            "date":             "$_id.date",
            "device_name":      "$_id.device",
            "total_energy_kWh": {"$round": ["$total_energy_kWh", 4]},
            "total_cost_EGP":   {"$round": ["$total_cost_EGP",   4]},
            "avg_power_W":      {"$round": ["$avg_power_W",       2]},
            "total_active_min": 1,
        }}
    ]

    results = list(data_col.aggregate(pipeline))
    return ok({"appliance_id": appliance_id, "count": len(results), "records": results})


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 2 — Weekly consumption
# GET /api/analytics/:applianceId/weekly
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/<appliance_id>/weekly", methods=["GET"])
def weekly(appliance_id):
    match = resolve_filter(appliance_id)

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "year":   {"$isoWeekYear": {"$dateFromString": {"dateString": "$interval_start"}}},
                "week":   {"$isoWeek":     {"$dateFromString": {"dateString": "$interval_start"}}},
                "device": "$device_name"
            },
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
            "avg_power_W":      {"$avg": "$avg_power_W"},
        }},
        {"$sort": {"_id.year": 1, "_id.week": 1, "_id.device": 1}},
        {"$project": {
            "_id": 0,
            "year":             "$_id.year",
            "week":             "$_id.week",
            "device_name":      "$_id.device",
            "total_energy_kWh": {"$round": ["$total_energy_kWh", 4]},
            "total_cost_EGP":   {"$round": ["$total_cost_EGP",   4]},
            "avg_power_W":      {"$round": ["$avg_power_W",       2]},
        }}
    ]

    results = list(data_col.aggregate(pipeline))
    return ok({"appliance_id": appliance_id, "count": len(results), "records": results})


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 3 — Monthly consumption and cost
# GET /api/analytics/:applianceId/monthly
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/<appliance_id>/monthly", methods=["GET"])
def monthly(appliance_id):
    match = resolve_filter(appliance_id)

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "year":   {"$year":  {"$dateFromString": {"dateString": "$interval_start"}}},
                "month":  {"$month": {"$dateFromString": {"dateString": "$interval_start"}}},
                "device": "$device_name"
            },
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
            "avg_power_W":      {"$avg": "$avg_power_W"},
            "record_count":     {"$sum": 1},
        }},
        {"$sort": {"_id.year": 1, "_id.month": 1, "_id.device": 1}},
        {"$project": {
            "_id": 0,
            "year":    "$_id.year",
            "month":   "$_id.month",
            "month_name": {"$arrayElemAt": [
                ["", "January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"],
                "$_id.month"
            ]},
            "device_name":      "$_id.device",
            "total_energy_kWh": {"$round": ["$total_energy_kWh", 4]},
            "total_cost_EGP":   {"$round": ["$total_cost_EGP",   4]},
            "avg_power_W":      {"$round": ["$avg_power_W",       2]},
            "record_count":     1,
        }}
    ]

    results = list(data_col.aggregate(pipeline))
    return ok({"appliance_id": appliance_id, "count": len(results), "records": results})


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 4 — Peak usage hours
# GET /api/analytics/:applianceId/peak-hours
# Query params: ?limit=5  (default 5, max 24)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/<appliance_id>/peak-hours", methods=["GET"])
def peak_hours(appliance_id):
    match = resolve_filter(appliance_id)
    limit = min(int(request.args.get("limit", 5)), 24)

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "hour":   {"$hour": {"$dateFromString": {"dateString": "$interval_start"}}},
                "device": "$device_name"
            },
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "avg_power_W":      {"$avg": "$avg_power_W"},
            "total_active_min": {"$sum": "$active_minutes"},
        }},
        {"$sort": {"total_energy_kWh": -1}},
        {"$limit": limit},
        {"$project": {
            "_id": 0,
            "hour":             "$_id.hour",
            "hour_label":       {"$concat": [{"$toString": "$_id.hour"}, ":00"]},
            "device_name":      "$_id.device",
            "total_energy_kWh": {"$round": ["$total_energy_kWh", 4]},
            "avg_power_W":      {"$round": ["$avg_power_W",       2]},
            "total_active_min": 1,
        }}
    ]

    results = list(data_col.aggregate(pipeline))
    return ok({"appliance_id": appliance_id, "top_n": limit, "count": len(results), "records": results})


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 5 — Total cost across all appliances
# GET /api/analytics/total/cost
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/total/cost", methods=["GET"])
def total_cost():
    per_device = list(data_col.aggregate([
        {"$group": {
            "_id":              "$device_name",
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
            "avg_power_W":      {"$avg": "$avg_power_W"},
        }},
        {"$sort": {"total_cost_EGP": -1}},
        {"$project": {
            "_id": 0,
            "device_name":      "$_id",
            "total_energy_kWh": {"$round": ["$total_energy_kWh", 4]},
            "total_cost_EGP":   {"$round": ["$total_cost_EGP",   4]},
            "avg_power_W":      {"$round": ["$avg_power_W",       2]},
        }}
    ]))

    grand = next(data_col.aggregate([
        {"$group": {
            "_id":              None,
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
        }}
    ]), {"total_energy_kWh": 0, "total_cost_EGP": 0})

    grand_cost = grand["total_cost_EGP"] or 1

    # Add cost share percentage to each device
    for d in per_device:
        d["share_of_total_pct"] = round(d["total_cost_EGP"] / grand_cost * 100, 1)

    first = data_col.find_one(sort=[("interval_start",  1)])
    last  = data_col.find_one(sort=[("interval_start", -1)])

    return ok({
        "grand_total_energy_kWh": round(grand["total_energy_kWh"], 4),
        "grand_total_cost_EGP":   round(grand["total_cost_EGP"],   4),
        "data_from":  first["interval_start"] if first else None,
        "data_to":    last["interval_start"]  if last  else None,
        "per_device": per_device,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 6 — Anomaly alerts
# GET /api/analytics/anomalies
# Query params:
#   ?device=Microwave
#   ?sort=score|time     (default: score — most severe first)
#   ?limit=50  ?offset=0
#   ?from=YYYY-MM-DD  ?to=YYYY-MM-DD
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/anomalies", methods=["GET"])
def anomalies():
    device    = request.args.get("device")
    sort_by   = request.args.get("sort", "score")   # "score" or "time"
    limit     = min(int(request.args.get("limit",  50)), 200)
    offset    = int(request.args.get("offset", 0))
    date_from = request.args.get("from")
    date_to   = request.args.get("to")

    query = {}
    if device:
        query["device_name"] = {"$regex": f"^{device}$", "$options": "i"}
    if date_from or date_to:
        query.setdefault("interval_start", {})
        if date_from:
            query["interval_start"]["$gte"] = f"{date_from}T00:00:00Z"
        if date_to:
            query["interval_start"]["$lte"] = f"{date_to}T23:59:59Z"

    # Sort: by anomaly severity (lowest score = most anomalous) or by time
    sort_field = "anomaly_score" if sort_by == "score" else "interval_start"
    sort_dir   = 1 if sort_by == "score" else -1   # score asc, time desc

    total_count = alerts_col.count_documents(query)
    records     = list(
        alerts_col.find(query, {"_id": 0})
        .sort(sort_field, sort_dir)
        .skip(offset)
        .limit(limit)
    )

    # Summary by device with share percentage
    summary_raw = list(alerts_col.aggregate([
        {"$match": query},
        {"$group": {
            "_id":         "$device_name",
            "count":       {"$sum": 1},
            "avg_score":   {"$avg": "$anomaly_score"},
            "worst_score": {"$min": "$anomaly_score"},
        }},
        {"$sort": {"count": -1}}
    ]))

    total_alerts = sum(s["count"] for s in summary_raw) or 1
    by_device = [
        {
            "device_name":        s["_id"],
            "alert_count":        s["count"],
            "share_pct":          round(s["count"] / total_alerts * 100, 1),
            "avg_score":          round(s["avg_score"],   6),
            "worst_score":        round(s["worst_score"], 6),
        }
        for s in summary_raw
    ]

    return ok({
        "total_alerts": total_count,
        "returned":     len(records),
        "offset":       offset,
        "limit":        limit,
        "sort":         sort_by,
        "by_device":    by_device,
        "alerts":       records,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 7 — Projected monthly bill
# GET /api/analytics/bill-estimate
# Query params: ?days=30  (projection window, default 30)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/bill-estimate", methods=["GET"])
def bill_estimate():
    projection_days = int(request.args.get("days", 30))

    result = next(data_col.aggregate([
        {"$group": {
            "_id": {"$dateToString": {
                "format": "%Y-%m-%d",
                "date":   {"$dateFromString": {"dateString": "$interval_start"}}
            }},
            "day_cost_EGP":   {"$sum": "$total_cost_EGP"},
            "day_energy_kWh": {"$sum": "$total_energy_kWh"},
        }},
        {"$group": {
            "_id":                  None,
            "avg_daily_cost_EGP":   {"$avg": "$day_cost_EGP"},
            "avg_daily_energy_kWh": {"$avg": "$day_energy_kWh"},
            "total_days":           {"$sum": 1},
            "total_cost_EGP":       {"$sum": "$day_cost_EGP"},
        }}
    ]), None)

    if not result:
        return err("Not enough data to estimate bill")

    avg_daily_cost   = result["avg_daily_cost_EGP"]
    avg_daily_energy = result["avg_daily_energy_kWh"]
    grand_cost       = result["total_cost_EGP"] or 1

    # Per-device projection
    device_totals = list(data_col.aggregate([
        {"$group": {
            "_id":            "$device_name",
            "total_cost_EGP": {"$sum": "$total_cost_EGP"},
            "total_energy":   {"$sum": "$total_energy_kWh"},
            "record_count":   {"$sum": 1},
        }},
        {"$sort": {"total_cost_EGP": -1}}
    ]))

    per_device = []
    for d in device_totals:
        days_of_data = d["record_count"] / 48     # 48 intervals per day
        daily_cost   = d["total_cost_EGP"] / max(days_of_data, 1)
        daily_energy = d["total_energy"]   / max(days_of_data, 1)
        per_device.append({
            "device_name":          d["_id"],
            "projected_cost_EGP":   round(daily_cost   * projection_days, 2),
            "projected_energy_kWh": round(daily_energy * projection_days, 4),
            "share_of_total_pct":   round(d["total_cost_EGP"] / grand_cost * 100, 1),
            "avg_daily_cost_EGP":   round(daily_cost,   4),
            "avg_daily_energy_kWh": round(daily_energy, 4),
        })

    return ok({
        "projection_days":          projection_days,
        "based_on_days_of_data":    result["total_days"],
        "projected_total_cost_EGP": round(avg_daily_cost   * projection_days, 2),
        "projected_energy_kWh":     round(avg_daily_energy * projection_days, 4),
        "avg_daily_cost_EGP":       round(avg_daily_cost,   4),
        "avg_daily_energy_kWh":     round(avg_daily_energy, 4),
        "per_device":               per_device,
    })


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🚀 Smart Home Analytics API")
    print("=" * 45)
    print("  GET /api/health")
    print("  GET /api/analytics/summary            ← NEW")
    print("  GET /api/analytics/<id>/daily")
    print("  GET /api/analytics/<id>/weekly")
    print("  GET /api/analytics/<id>/monthly")
    print("  GET /api/analytics/<id>/peak-hours")
    print("  GET /api/analytics/total/cost")
    print("  GET /api/analytics/anomalies")
    print("  GET /api/analytics/bill-estimate")
    print("\nQuick test URLs:")
    print("  http://127.0.0.1:5000/api/health")
    print("  http://127.0.0.1:5000/api/analytics/summary")
    print("  http://127.0.0.1:5000/api/analytics/all/daily")
    print("  http://127.0.0.1:5000/api/analytics/anomalies?sort=time")
    print("  http://127.0.0.1:5000/api/analytics/anomalies?device=Microwave")
    print("  http://127.0.0.1:5000/api/analytics/bill-estimate?days=30")
    print("=" * 45 + "\n")

    app.run(debug=False, host="127.0.0.1", port=5000)