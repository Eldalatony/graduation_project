"""
api.py
------
Analytics API — Smart Home Energy Monitoring System
Phase 4 | Production-ready

Improvements in this version:
  - Severity levels (low / medium / high / critical) on all anomaly responses
  - Anomaly rate percentage on summary and anomaly endpoints
  - Pagination on daily endpoint (?page=1&page_size=30)
  - Consistent field naming throughout (active_minutes everywhere)
  - Input validation with clear error messages on all endpoints
  - Structured logging (timestamp, method, path, status, duration)
  - Consistent response rounding and structure
  - share_of_total_pct on all cost breakdowns

Endpoints:
  GET /api/health
  GET /api/analytics/summary
  GET /api/analytics/:applianceId/daily        ?from  ?to  ?page  ?page_size
  GET /api/analytics/:applianceId/weekly       ?from  ?to
  GET /api/analytics/:applianceId/monthly
  GET /api/analytics/:applianceId/peak-hours   ?limit
  GET /api/analytics/total/cost
  GET /api/analytics/anomalies                 ?device  ?severity  ?sort  ?limit  ?offset  ?from  ?to
  GET /api/analytics/bill-estimate             ?days

Run:
  pip install flask flask-cors
  python api.py
"""

from flask import Flask, jsonify, request, send_file, g
from flask_cors import CORS
import pymongo
import logging
import time
import io
from datetime import datetime, timezone

# ── Logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("smart_home_api")

# ── Config ────────────────────────────────────────────────────────────────────

MONGO_URI = "mongodb://admin:admin123@ac-smxdtmy-shard-00-00.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-01.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-02.nvratez.mongodb.net:27017/?ssl=true&replicaSet=atlas-12lqnf-shard-0&authSource=admin&appName=Cluster0"

VALID_SORT_OPTIONS    = {"score", "time"}
VALID_SEVERITY_LEVELS = {"low", "medium", "high", "critical"}
MAX_PAGE_SIZE         = 100
MAX_LIMIT             = 200

# Severity thresholds — anomaly_score is negative; more negative = worse
# These map score ranges to human-readable severity levels
SEVERITY_THRESHOLDS = {
    "critical": -0.07,   # score ≤ -0.07
    "high":     -0.04,   # -0.07 < score ≤ -0.04
    "medium":   -0.015,  # -0.04 < score ≤ -0.015
    "low":       0.0,    # -0.015 < score ≤ 0  (anything flagged but mild)
}

def score_to_severity(score: float) -> str:
    if score <= SEVERITY_THRESHOLDS["critical"]:
        return "critical"
    if score <= SEVERITY_THRESHOLDS["high"]:
        return "high"
    if score <= SEVERITY_THRESHOLDS["medium"]:
        return "medium"
    return "low"

# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

client     = pymongo.MongoClient(MONGO_URI)
db         = client["smart_home"]
data_col   = db["appliance_data"]
alerts_col = db["anomaly_alerts"]

# ── Request / response logging ────────────────────────────────────────────────

@app.before_request
def before_request():
    g.start_time = time.time()

@app.after_request
def after_request(response):
    duration_ms = round((time.time() - g.start_time) * 1000, 1)
    if request.path != "/favicon.ico":
        log.info(f"{request.method} {request.path}  →  {response.status_code}  ({duration_ms}ms)")
    return response

# ── Response helpers ──────────────────────────────────────────────────────────

def ok(data):
    return jsonify({"status": "ok", "data": data})

def err(message, code=400):
    log.warning(f"Bad request [{code}]: {message}")
    return jsonify({"status": "error", "message": message}), code

# ── Input validation helpers ──────────────────────────────────────────────────

def validate_date(value: str, param_name: str):
    """Returns (date_str, None) or (None, error_response)."""
    if not value:
        return None, None
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value, None
    except ValueError:
        return None, err(f"'{param_name}' must be in YYYY-MM-DD format, got: '{value}'")

def validate_int(value, param_name: str, min_val: int, max_val: int, default: int):
    """Returns (int_val, None) or (None, error_response)."""
    if value is None:
        return default, None
    try:
        v = int(value)
        if not (min_val <= v <= max_val):
            return None, err(f"'{param_name}' must be between {min_val} and {max_val}, got: {v}")
        return v, None
    except ValueError:
        return None, err(f"'{param_name}' must be an integer, got: '{value}'")

def validate_appliance_id(appliance_id: str):
    """Returns (filter_dict, None) or (None, error_response)."""
    if not appliance_id or len(appliance_id) > 100:
        return None, err("Invalid appliance ID")
    if appliance_id.lower() == "all":
        return {}, None
    if data_col.find_one({"node_key": appliance_id}):
        return {"node_key": appliance_id}, None
    if data_col.find_one({"device_name": {"$regex": f"^{appliance_id}$", "$options": "i"}}):
        return {"device_name": {"$regex": f"^{appliance_id}$", "$options": "i"}}, None
    return None, err(f"Appliance not found: '{appliance_id}'", 404)

# ── Favicon silencer ──────────────────────────────────────────────────────────

@app.route("/favicon.ico")
def favicon():
    transparent_png = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        b'\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
        b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
        b'\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    return send_file(io.BytesIO(transparent_png), mimetype="image/png")

# ── 404 handler ───────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return err(f"Endpoint not found: {request.path}", 404)

@app.errorhandler(405)
def method_not_allowed(e):
    return err(f"Method {request.method} not allowed on {request.path}", 405)

@app.errorhandler(500)
def internal_error(e):
    log.error(f"Internal error: {e}")
    return err("Internal server error", 500)


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
        log.error(f"Health check failed: {e}")
        return err(f"Database unreachable: {e}", 503)


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD SUMMARY
# GET /api/analytics/summary
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/summary", methods=["GET"])
def summary():
    # Grand totals
    grand = next(data_col.aggregate([
        {"$group": {
            "_id":              None,
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
            "total_records":    {"$sum": 1},
        }}
    ]), {"total_energy_kWh": 0, "total_cost_EGP": 0, "total_records": 0})

    grand_cost = grand["total_cost_EGP"] or 1

    # Per-device breakdown with share
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

    per_device = [
        {
            "device_name":        d["_id"],
            "total_energy_kWh":   round(d["total_energy_kWh"], 4),
            "total_cost_EGP":     round(d["total_cost_EGP"],   2),
            "avg_power_W":        round(d["avg_power_W"],       1),
            "share_of_total_pct": round(d["total_cost_EGP"] / grand_cost * 100, 1),
        }
        for d in device_totals
    ]

    # Projected 30-day bill
    daily_agg = next(data_col.aggregate([
        {"$group": {
            "_id":      {"$dateToString": {"format": "%Y-%m-%d", "date": {"$dateFromString": {"dateString": "$interval_start"}}}},
            "day_cost": {"$sum": "$total_cost_EGP"},
        }},
        {"$group": {
            "_id":            None,
            "avg_daily_cost": {"$avg": "$day_cost"},
            "total_days":     {"$sum": 1},
        }}
    ]), {"avg_daily_cost": 0, "total_days": 0})

    projected_bill = round(daily_agg["avg_daily_cost"] * 30, 2)

    # Anomaly summary with severity counts
    total_records = grand["total_records"] or 1
    alert_count   = alerts_col.count_documents({})
    anomaly_rate  = round(alert_count / total_records * 100, 3)

    raw_alerts = list(alerts_col.find({}, {"_id": 0, "anomaly_score": 1, "device_name": 1}))
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in raw_alerts:
        severity_counts[score_to_severity(a["anomaly_score"])] += 1

    alerts_by_device = list(alerts_col.aggregate([
        {"$group": {
            "_id":         "$device_name",
            "count":       {"$sum": 1},
            "worst_score": {"$min": "$anomaly_score"},
        }},
        {"$sort": {"count": -1}}
    ]))

    most_severe = alerts_col.find_one(
        {}, {"_id": 0, "device_name": 1, "interval_start": 1,
             "avg_power_W": 1, "anomaly_score": 1, "ground_truth_anomaly": 1},
        sort=[("anomaly_score", 1)]
    )
    if most_severe:
        most_severe["severity"] = score_to_severity(most_severe["anomaly_score"])

    # Top 3 peak hours
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
            "hour_label":       {"$concat": [{"$toString": "$_id"}, ":00"]},
            "total_energy_kWh": {"$round": ["$total_energy_kWh", 3]},
        }}
    ]))

    first = data_col.find_one(sort=[("interval_start",  1)])
    last  = data_col.find_one(sort=[("interval_start", -1)])

    return ok({
        "data_range": {
            "from": first["interval_start"] if first else None,
            "to":   last["interval_start"]  if last  else None,
            "days": daily_agg["total_days"],
        },
        "totals": {
            "energy_kWh": round(grand["total_energy_kWh"], 4),
            "cost_EGP":   round(grand["total_cost_EGP"],   2),
        },
        "projected_monthly_bill_EGP": projected_bill,
        "per_device": per_device,
        "anomalies": {
            "total_alerts":     alert_count,
            "anomaly_rate_pct": anomaly_rate,
            "severity_counts":  severity_counts,
            "by_device": [
                {
                    "device_name": a["_id"],
                    "count":       a["count"],
                    "worst_score": round(a["worst_score"], 6),
                    "severity":    score_to_severity(a["worst_score"]),
                }
                for a in alerts_by_device
            ],
            "most_severe_alert": most_severe,
        },
        "peak_hours": peak,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 1 — Daily consumption  (paginated)
# GET /api/analytics/:applianceId/daily
# Query params: ?from  ?to  ?page=1  ?page_size=30
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/<appliance_id>/daily", methods=["GET"])
def daily(appliance_id):
    match, e = validate_appliance_id(appliance_id)
    if e: return e

    date_from, e = validate_date(request.args.get("from"), "from")
    if e: return e
    date_to,   e = validate_date(request.args.get("to"),   "to")
    if e: return e
    page,      e = validate_int(request.args.get("page"),      "page",      1, 9999, 1)
    if e: return e
    page_size, e = validate_int(request.args.get("page_size"), "page_size", 1, MAX_PAGE_SIZE, 30)
    if e: return e

    if date_from or date_to:
        match.setdefault("interval_start", {})
        if date_from: match["interval_start"]["$gte"] = f"{date_from}T00:00:00Z"
        if date_to:   match["interval_start"]["$lte"] = f"{date_to}T23:59:59Z"

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "date":   {"$dateToString": {"format": "%Y-%m-%d", "date": {"$dateFromString": {"dateString": "$interval_start"}}}},
                "device": "$device_name"
            },
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
            "avg_power_W":      {"$avg": "$avg_power_W"},
            "active_minutes":   {"$sum": "$active_minutes"},    # consistent name
        }},
        {"$sort": {"_id.date": 1, "_id.device": 1}},
        {"$project": {
            "_id": 0,
            "date":             "$_id.date",
            "device_name":      "$_id.device",
            "total_energy_kWh": {"$round": ["$total_energy_kWh", 4]},
            "total_cost_EGP":   {"$round": ["$total_cost_EGP",   2]},
            "avg_power_W":      {"$round": ["$avg_power_W",       1]},
            "active_minutes":   1,
        }},
        {"$skip":  (page - 1) * page_size},
        {"$limit": page_size},
    ]

    # Count total for pagination metadata (without skip/limit)
    count_pipeline = [
        {"$match": match},
        {"$group": {"_id": {"date": {"$dateToString": {"format": "%Y-%m-%d", "date": {"$dateFromString": {"dateString": "$interval_start"}}}}, "device": "$device_name"}}},
        {"$count": "total"}
    ]
    total_records = next(data_col.aggregate(count_pipeline), {}).get("total", 0)
    total_pages   = max(1, -(-total_records // page_size))   # ceiling division

    results = list(data_col.aggregate(pipeline))
    return ok({
        "appliance_id": appliance_id,
        "pagination": {
            "page":          page,
            "page_size":     page_size,
            "total_records": total_records,
            "total_pages":   total_pages,
        },
        "count":   len(results),
        "records": results,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 2 — Weekly consumption
# GET /api/analytics/:applianceId/weekly
# Query params: ?from  ?to
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/<appliance_id>/weekly", methods=["GET"])
def weekly(appliance_id):
    match, e = validate_appliance_id(appliance_id)
    if e: return e

    date_from, e = validate_date(request.args.get("from"), "from")
    if e: return e
    date_to,   e = validate_date(request.args.get("to"),   "to")
    if e: return e

    if date_from or date_to:
        match.setdefault("interval_start", {})
        if date_from: match["interval_start"]["$gte"] = f"{date_from}T00:00:00Z"
        if date_to:   match["interval_start"]["$lte"] = f"{date_to}T23:59:59Z"

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
            "active_minutes":   {"$sum": "$active_minutes"},
        }},
        {"$sort": {"_id.year": 1, "_id.week": 1, "_id.device": 1}},
        {"$project": {
            "_id": 0,
            "year":             "$_id.year",
            "week":             "$_id.week",
            "device_name":      "$_id.device",
            "total_energy_kWh": {"$round": ["$total_energy_kWh", 4]},
            "total_cost_EGP":   {"$round": ["$total_cost_EGP",   2]},
            "avg_power_W":      {"$round": ["$avg_power_W",       1]},
            "active_minutes":   1,
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
    match, e = validate_appliance_id(appliance_id)
    if e: return e

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
            "active_minutes":   {"$sum": "$active_minutes"},
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
            "total_cost_EGP":   {"$round": ["$total_cost_EGP",   2]},
            "avg_power_W":      {"$round": ["$avg_power_W",       1]},
            "active_minutes":   1,
            "record_count":     1,
        }}
    ]

    results = list(data_col.aggregate(pipeline))
    return ok({"appliance_id": appliance_id, "count": len(results), "records": results})


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 4 — Peak usage hours
# GET /api/analytics/:applianceId/peak-hours
# Query params: ?limit=5  (1–24)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/<appliance_id>/peak-hours", methods=["GET"])
def peak_hours(appliance_id):
    match, e = validate_appliance_id(appliance_id)
    if e: return e

    limit, e = validate_int(request.args.get("limit"), "limit", 1, 24, 5)
    if e: return e

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "hour":   {"$hour": {"$dateFromString": {"dateString": "$interval_start"}}},
                "device": "$device_name"
            },
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "avg_power_W":      {"$avg": "$avg_power_W"},
            "active_minutes":   {"$sum": "$active_minutes"},
        }},
        {"$sort": {"total_energy_kWh": -1}},
        {"$limit": limit},
        {"$project": {
            "_id": 0,
            "hour":             "$_id.hour",
            "hour_label":       {"$concat": [{"$toString": "$_id.hour"}, ":00"]},
            "device_name":      "$_id.device",
            "total_energy_kWh": {"$round": ["$total_energy_kWh", 4]},
            "avg_power_W":      {"$round": ["$avg_power_W",       1]},
            "active_minutes":   1,
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
    per_device_raw = list(data_col.aggregate([
        {"$group": {
            "_id":              "$device_name",
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
            "avg_power_W":      {"$avg": "$avg_power_W"},
        }},
        {"$sort": {"total_cost_EGP": -1}}
    ]))

    grand = next(data_col.aggregate([
        {"$group": {
            "_id":              None,
            "total_energy_kWh": {"$sum": "$total_energy_kWh"},
            "total_cost_EGP":   {"$sum": "$total_cost_EGP"},
        }}
    ]), {"total_energy_kWh": 0, "total_cost_EGP": 0})

    grand_cost = grand["total_cost_EGP"] or 1

    per_device = [
        {
            "device_name":        d["_id"],
            "total_energy_kWh":   round(d["total_energy_kWh"], 4),
            "total_cost_EGP":     round(d["total_cost_EGP"],   2),
            "avg_power_W":        round(d["avg_power_W"],       1),
            "share_of_total_pct": round(d["total_cost_EGP"] / grand_cost * 100, 1),
        }
        for d in per_device_raw
    ]

    first = data_col.find_one(sort=[("interval_start",  1)])
    last  = data_col.find_one(sort=[("interval_start", -1)])

    return ok({
        "grand_total_energy_kWh": round(grand["total_energy_kWh"], 4),
        "grand_total_cost_EGP":   round(grand["total_cost_EGP"],   2),
        "data_from":  first["interval_start"] if first else None,
        "data_to":    last["interval_start"]  if last  else None,
        "per_device": per_device,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 6 — Anomaly alerts
# GET /api/analytics/anomalies
# Query params:
#   ?device=Microwave
#   ?severity=low|medium|high|critical
#   ?sort=score|time          (default: score)
#   ?limit=50  ?offset=0
#   ?from=YYYY-MM-DD  ?to=YYYY-MM-DD
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/anomalies", methods=["GET"])
def anomalies():
    device   = request.args.get("device")
    severity = request.args.get("severity", "").lower() or None
    sort_by  = request.args.get("sort", "score").lower()

    limit,  e = validate_int(request.args.get("limit"),  "limit",  1, MAX_LIMIT, 50)
    if e: return e
    offset, e = validate_int(request.args.get("offset"), "offset", 0, 999999, 0)
    if e: return e

    date_from, e = validate_date(request.args.get("from"), "from")
    if e: return e
    date_to,   e = validate_date(request.args.get("to"),   "to")
    if e: return e

    if sort_by not in VALID_SORT_OPTIONS:
        return err(f"'sort' must be one of: {sorted(VALID_SORT_OPTIONS)}")
    if severity and severity not in VALID_SEVERITY_LEVELS:
        return err(f"'severity' must be one of: {sorted(VALID_SEVERITY_LEVELS)}")

    # Build query
    query = {}
    if device:
        query["device_name"] = {"$regex": f"^{device}$", "$options": "i"}
    if date_from or date_to:
        query.setdefault("interval_start", {})
        if date_from: query["interval_start"]["$gte"] = f"{date_from}T00:00:00Z"
        if date_to:   query["interval_start"]["$lte"] = f"{date_to}T23:59:59Z"

    # Map severity filter to score range
    if severity:
        thresholds = {
            "critical": {"$lte": SEVERITY_THRESHOLDS["critical"]},
            "high":     {"$gt": SEVERITY_THRESHOLDS["critical"], "$lte": SEVERITY_THRESHOLDS["high"]},
            "medium":   {"$gt": SEVERITY_THRESHOLDS["high"],     "$lte": SEVERITY_THRESHOLDS["medium"]},
            "low":      {"$gt": SEVERITY_THRESHOLDS["medium"],   "$lte": 0},
        }
        query["anomaly_score"] = thresholds[severity]

    sort_field = "anomaly_score" if sort_by == "score" else "interval_start"
    sort_dir   = 1 if sort_by == "score" else -1

    total_count  = alerts_col.count_documents(query)
    total_records = data_col.count_documents({}) or 1
    anomaly_rate  = round(total_count / total_records * 100, 3)

    records = list(
        alerts_col.find(query, {"_id": 0})
        .sort(sort_field, sort_dir)
        .skip(offset)
        .limit(limit)
    )

    # Add severity label to each alert
    for r in records:
        r["severity"] = score_to_severity(r["anomaly_score"])

    # Summary by device
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

    total_alerts_in_summary = sum(s["count"] for s in summary_raw) or 1
    by_device = [
        {
            "device_name": s["_id"],
            "alert_count": s["count"],
            "share_pct":   round(s["count"] / total_alerts_in_summary * 100, 1),
            "avg_score":   round(s["avg_score"],   6),
            "worst_score": round(s["worst_score"], 6),
            "severity":    score_to_severity(s["worst_score"]),
        }
        for s in summary_raw
    ]

    # Severity count breakdown
    all_scores = [a["anomaly_score"] for a in alerts_col.find(query, {"_id": 0, "anomaly_score": 1})]
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for sc in all_scores:
        severity_counts[score_to_severity(sc)] += 1

    return ok({
        "total_alerts":     total_count,
        "anomaly_rate_pct": anomaly_rate,
        "returned":         len(records),
        "offset":           offset,
        "limit":            limit,
        "sort":             sort_by,
        "severity_filter":  severity,
        "severity_counts":  severity_counts,
        "by_device":        by_device,
        "alerts":           records,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 7 — Projected monthly bill
# GET /api/analytics/bill-estimate
# Query params: ?days=30  (1–365)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/analytics/bill-estimate", methods=["GET"])
def bill_estimate():
    projection_days, e = validate_int(request.args.get("days"), "days", 1, 365, 30)
    if e: return e

    result = next(data_col.aggregate([
        {"$group": {
            "_id":      {"$dateToString": {"format": "%Y-%m-%d", "date": {"$dateFromString": {"dateString": "$interval_start"}}}},
            "day_cost": {"$sum": "$total_cost_EGP"},
            "day_kwh":  {"$sum": "$total_energy_kWh"},
        }},
        {"$group": {
            "_id":            None,
            "avg_daily_cost": {"$avg": "$day_cost"},
            "avg_daily_kwh":  {"$avg": "$day_kwh"},
            "total_days":     {"$sum": 1},
            "total_cost":     {"$sum": "$day_cost"},
        }}
    ]), None)

    if not result:
        return err("Not enough data to estimate bill")

    grand_cost = result["total_cost"] or 1

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
        days_of_data = d["record_count"] / 48
        daily_cost   = d["total_cost_EGP"] / max(days_of_data, 1)
        daily_energy = d["total_energy"]   / max(days_of_data, 1)
        per_device.append({
            "device_name":          d["_id"],
            "projected_cost_EGP":   round(daily_cost   * projection_days, 2),
            "projected_energy_kWh": round(daily_energy * projection_days, 4),
            "share_of_total_pct":   round(d["total_cost_EGP"] / grand_cost * 100, 1),
            "avg_daily_cost_EGP":   round(daily_cost,   2),
            "avg_daily_energy_kWh": round(daily_energy, 4),
        })

    return ok({
        "projection_days":          projection_days,
        "based_on_days_of_data":    result["total_days"],
        "projected_total_cost_EGP": round(result["avg_daily_cost"] * projection_days, 2),
        "projected_energy_kWh":     round(result["avg_daily_kwh"]  * projection_days, 4),
        "avg_daily_cost_EGP":       round(result["avg_daily_cost"], 2),
        "avg_daily_energy_kWh":     round(result["avg_daily_kwh"],  4),
        "per_device":               per_device,
    })


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🚀 Smart Home Analytics API  —  Production Ready")
    print("=" * 50)
    print("  GET /api/health")
    print("  GET /api/analytics/summary")
    print("  GET /api/analytics/<id>/daily        ?from ?to ?page ?page_size")
    print("  GET /api/analytics/<id>/weekly       ?from ?to")
    print("  GET /api/analytics/<id>/monthly")
    print("  GET /api/analytics/<id>/peak-hours   ?limit")
    print("  GET /api/analytics/total/cost")
    print("  GET /api/analytics/anomalies         ?device ?severity ?sort ?limit ?offset ?from ?to")
    print("  GET /api/analytics/bill-estimate     ?days")
    print("\nSeverity levels: low | medium | high | critical")
    print("Appliance IDs:   all | node_1..node_5 | device name")
    print("=" * 50 + "\n")

    app.run(debug=False, host="127.0.0.1", port=5000)