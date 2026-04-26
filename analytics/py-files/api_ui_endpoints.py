"""
api_ui_endpoints.py
-------------------
Add these endpoints to your existing api.py to make it fully frontend-ready.
These endpoints return data shaped exactly for chart libraries (Chart.js,
Recharts, ApexCharts) — no transformation needed on the frontend side.

New endpoints:
  GET /api/ui/dashboard          — everything the dashboard page needs in 1 call
  GET /api/ui/charts/energy-trend   ?granularity=daily|weekly|monthly
  GET /api/ui/charts/cost-breakdown — donut/bar chart data per device
  GET /api/ui/charts/peak-hours     — bar chart of 24 hours
  GET /api/ui/anomalies/feed        — alert panel with severity badges
  GET /api/ui/anomalies/heatmap     — device × day anomaly heatmap data

Mount in api.py:
  from api_ui_endpoints import ui_bp
  app.register_blueprint(ui_bp)
"""

from flask import Blueprint, jsonify, request
import pymongo
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────

MONGO_URI = "mongodb://admin:admin123@ac-smxdtmy-shard-00-00.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-01.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-02.nvratez.mongodb.net:27017/?ssl=true&replicaSet=atlas-12lqnf-shard-0&authSource=admin&appName=Cluster0"

SEVERITY_THRESHOLDS = {
    "critical": -0.07,
    "high":     -0.04,
    "medium":   -0.015,
    "low":       0.0,
}

SEVERITY_COLORS = {
    "critical": "#ef4444",   # red
    "high":     "#f97316",   # orange
    "medium":   "#eab308",   # yellow
    "low":      "#3b82f6",   # blue
}

DEVICE_COLORS = [
    "#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#ef4444",
    "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#84cc16",
]

def score_to_severity(score: float) -> str:
    if score <= SEVERITY_THRESHOLDS["critical"]: return "critical"
    if score <= SEVERITY_THRESHOLDS["high"]:     return "high"
    if score <= SEVERITY_THRESHOLDS["medium"]:   return "medium"
    return "low"

# ── DB connection ─────────────────────────────────────────────────────────────

client     = pymongo.MongoClient(MONGO_URI)
db         = client["smart_home"]
data_col   = db["appliance_data"]
alerts_col = db["anomaly_alerts"]

ui_bp = Blueprint("ui", __name__)

def ok(data):
    return jsonify({"status": "ok", "data": data})

def err(msg, code=400):
    return jsonify({"status": "error", "message": msg}), code


# ═══════════════════════════════════════════════════════════════════════════════
# /api/ui/dashboard
# Single call that returns EVERYTHING the main dashboard page needs.
# Eliminates multiple round-trips from the frontend.
# ═══════════════════════════════════════════════════════════════════════════════

@ui_bp.route("/api/ui/dashboard", methods=["GET"])
def ui_dashboard():
    """
    Returns all dashboard data in one response.

    Frontend usage:
      const { data } = await fetch('/api/ui/dashboard').then(r => r.json())
      // data.kpi_cards      → 4 top summary cards
      // data.cost_donut     → donut chart (cost share per device)
      // data.energy_trend   → line chart (daily energy over time)
      // data.peak_hours     → bar chart (energy by hour)
      // data.anomaly_summary → alert panel summary
      // data.recent_alerts  → last 5 alerts for notification widget
    """

    # ── KPI cards ─────────────────────────────────────────────────────────────
    grand = next(data_col.aggregate([
        {"$group": {
            "_id": None,
            "total_energy": {"$sum": "$total_energy_kWh"},
            "total_cost":   {"$sum": "$total_cost_EGP"},
            "total_records": {"$sum": 1},
        }}
    ]), {"total_energy": 0, "total_cost": 0, "total_records": 0})

    daily_avg = next(data_col.aggregate([
        {"$group": {
            "_id":      {"$dateToString": {"format": "%Y-%m-%d", "date": {"$dateFromString": {"dateString": "$interval_start"}}}},
            "day_cost": {"$sum": "$total_cost_EGP"},
        }},
        {"$group": {"_id": None, "avg": {"$avg": "$day_cost"}, "days": {"$sum": 1}}}
    ]), {"avg": 0, "days": 0})

    alert_count = alerts_col.count_documents({})
    total_records = grand["total_records"] or 1

    kpi_cards = [
        {
            "id":       "total_energy",
            "label":    "Total Energy Consumed",
            "value":    round(grand["total_energy"], 2),
            "unit":     "kWh",
            "icon":     "bolt",
            "color":    "#6366f1",
        },
        {
            "id":       "total_cost",
            "label":    "Total Cost",
            "value":    round(grand["total_cost"], 2),
            "unit":     "EGP",
            "icon":     "currency",
            "color":    "#10b981",
        },
        {
            "id":       "projected_bill",
            "label":    "Projected Monthly Bill",
            "value":    round(daily_avg["avg"] * 30, 2),
            "unit":     "EGP",
            "icon":     "calendar",
            "color":    "#f59e0b",
        },
        {
            "id":       "anomaly_count",
            "label":    "Anomalies Detected",
            "value":    alert_count,
            "unit":     "alerts",
            "icon":     "warning",
            "color":    "#ef4444",
            "sub_label": f"{round(alert_count / total_records * 100, 2)}% alert rate",
        },
    ]

    # ── Cost donut chart ──────────────────────────────────────────────────────
    device_costs = list(data_col.aggregate([
        {"$group": {
            "_id":            "$device_name",
            "total_cost_EGP": {"$sum": "$total_cost_EGP"},
            "total_energy":   {"$sum": "$total_energy_kWh"},
        }},
        {"$sort": {"total_cost_EGP": -1}}
    ]))

    grand_cost = sum(d["total_cost_EGP"] for d in device_costs) or 1

    cost_donut = {
        "labels":   [d["_id"] for d in device_costs],
        "datasets": [{
            "label":           "Cost (EGP)",
            "data":            [round(d["total_cost_EGP"], 2) for d in device_costs],
            "backgroundColor": DEVICE_COLORS[:len(device_costs)],
            "borderWidth":     2,
            "borderColor":     "#ffffff",
        }],
        # Extra metadata per slice (for tooltips)
        "meta": [
            {
                "device":           d["_id"],
                "cost_EGP":         round(d["total_cost_EGP"], 2),
                "energy_kWh":       round(d["total_energy"], 4),
                "share_pct":        round(d["total_cost_EGP"] / grand_cost * 100, 1),
                "color":            DEVICE_COLORS[i % len(DEVICE_COLORS)],
            }
            for i, d in enumerate(device_costs)
        ],
    }

    # ── Daily energy trend (last 30 days) ─────────────────────────────────────
    daily_trend_raw = list(data_col.aggregate([
        {"$group": {
            "_id":    {"$dateToString": {"format": "%Y-%m-%d", "date": {"$dateFromString": {"dateString": "$interval_start"}}}},
            "energy": {"$sum": "$total_energy_kWh"},
            "cost":   {"$sum": "$total_cost_EGP"},
        }},
        {"$sort": {"_id": 1}},
        {"$limit": 30},
    ]))

    energy_trend = {
        "labels": [r["_id"] for r in daily_trend_raw],
        "datasets": [
            {
                "label":           "Energy (kWh)",
                "data":            [round(r["energy"], 4) for r in daily_trend_raw],
                "borderColor":     "#6366f1",
                "backgroundColor": "rgba(99,102,241,0.1)",
                "tension":         0.4,
                "fill":            True,
                "yAxisID":         "y",
            },
            {
                "label":           "Cost (EGP)",
                "data":            [round(r["cost"], 2) for r in daily_trend_raw],
                "borderColor":     "#10b981",
                "backgroundColor": "rgba(16,185,129,0.1)",
                "tension":         0.4,
                "fill":            False,
                "yAxisID":         "y1",
            },
        ],
    }

    # ── Peak hours bar chart (all 24 hours) ───────────────────────────────────
    hour_raw = list(data_col.aggregate([
        {"$group": {
            "_id":    {"$hour": {"$dateFromString": {"dateString": "$interval_start"}}},
            "energy": {"$sum": "$total_energy_kWh"},
        }},
        {"$sort": {"_id": 1}},
    ]))

    hour_map    = {r["_id"]: round(r["energy"], 3) for r in hour_raw}
    peak_values = [hour_map.get(h, 0) for h in range(24)]
    peak_max    = max(peak_values) if peak_values else 1

    peak_hours = {
        "labels": [f"{h:02d}:00" for h in range(24)],
        "datasets": [{
            "label":           "Energy (kWh)",
            "data":            peak_values,
            # Colour peaks darker — helps frontend without extra logic
            "backgroundColor": [
                "#6366f1" if v >= peak_max * 0.8
                else "#a5b4fc" if v >= peak_max * 0.5
                else "#e0e7ff"
                for v in peak_values
            ],
            "borderRadius":    4,
        }],
        "peak_hour":       peak_values.index(peak_max),
        "peak_hour_label": f"{peak_values.index(peak_max):02d}:00",
    }

    # ── Anomaly summary for alert panel ───────────────────────────────────────
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in alerts_col.find({}, {"anomaly_score": 1}):
        severity_counts[score_to_severity(a["anomaly_score"])] += 1

    anomaly_summary = {
        "total":    alert_count,
        "rate_pct": round(alert_count / total_records * 100, 3),
        "by_severity": [
            {
                "severity": sev,
                "count":    severity_counts[sev],
                "color":    SEVERITY_COLORS[sev],
            }
            for sev in ["critical", "high", "medium", "low"]
        ],
    }

    # ── Recent alerts (last 5 for notification widget) ────────────────────────
    recent_raw = list(alerts_col.find(
        {}, {"_id": 0, "device_name": 1, "interval_start": 1,
             "avg_power_W": 1, "anomaly_score": 1, "ground_truth_anomaly": 1}
    ).sort("scored_at", -1).limit(5))

    recent_alerts = [
        {
            "device":         a["device_name"],
            "time":           a["interval_start"],
            "avg_power_W":    round(a["avg_power_W"], 1),
            "score":          round(a["anomaly_score"], 5),
            "severity":       score_to_severity(a["anomaly_score"]),
            "severity_color": SEVERITY_COLORS[score_to_severity(a["anomaly_score"])],
            "label":          a.get("ground_truth_anomaly") or "Unclassified",
        }
        for a in recent_raw
    ]

    return ok({
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "kpi_cards":      kpi_cards,
        "cost_donut":     cost_donut,
        "energy_trend":   energy_trend,
        "peak_hours":     peak_hours,
        "anomaly_summary": anomaly_summary,
        "recent_alerts":  recent_alerts,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# /api/ui/charts/energy-trend
# Line chart data with daily / weekly / monthly granularity.
# Each device gets its own dataset line.
# ═══════════════════════════════════════════════════════════════════════════════

@ui_bp.route("/api/ui/charts/energy-trend", methods=["GET"])
def ui_energy_trend():
    """
    Query params:
      ?granularity=daily|weekly|monthly   (default: daily)

    Returns Chart.js multi-line dataset — one line per device.

    Example frontend usage (Chart.js):
      new Chart(ctx, { type: 'line', data: response.data.chart_data })
    """
    granularity = request.args.get("granularity", "daily").lower()
    if granularity not in ("daily", "weekly", "monthly"):
        return err("granularity must be daily, weekly, or monthly")

    if granularity == "daily":
        date_fmt  = "%Y-%m-%d"
        group_id  = {"$dateToString": {"format": date_fmt, "date": {"$dateFromString": {"dateString": "$interval_start"}}}}
        label_fmt = lambda r: r["_id"]["period"]
    elif granularity == "weekly":
        group_id  = {
            "period": {"$concat": [
                {"$toString": {"$isoWeekYear": {"$dateFromString": {"dateString": "$interval_start"}}}},
                "-W",
                {"$toString": {"$isoWeek": {"$dateFromString": {"dateString": "$interval_start"}}}}
            ]},
            "device": "$device_name",
        }
        label_fmt = lambda r: r["_id"]["period"]
    else:
        group_id  = {
            "period": {"$dateToString": {"format": "%Y-%m", "date": {"$dateFromString": {"dateString": "$interval_start"}}}},
            "device": "$device_name",
        }
        label_fmt = lambda r: r["_id"]["period"]

    pipeline = [
        {"$group": {
            "_id":    {"period": group_id, "device": "$device_name"} if granularity == "daily"
                      else {"period": group_id["period"] if granularity != "daily" else group_id,
                            "device": "$device_name"},
            "energy": {"$sum": "$total_energy_kWh"},
            "cost":   {"$sum": "$total_cost_EGP"},
        }},
        {"$sort": {"_id.period": 1}},
    ]

    # Simpler flat pipeline that works for all granularities
    if granularity == "daily":
        pipeline = [
            {"$group": {
                "_id": {
                    "period": {"$dateToString": {"format": "%Y-%m-%d", "date": {"$dateFromString": {"dateString": "$interval_start"}}}},
                    "device": "$device_name",
                },
                "energy": {"$sum": "$total_energy_kWh"},
                "cost":   {"$sum": "$total_cost_EGP"},
            }},
            {"$sort": {"_id.period": 1}},
        ]
    elif granularity == "weekly":
        pipeline = [
            {"$group": {
                "_id": {
                    "year":   {"$isoWeekYear": {"$dateFromString": {"dateString": "$interval_start"}}},
                    "week":   {"$isoWeek":     {"$dateFromString": {"dateString": "$interval_start"}}},
                    "device": "$device_name",
                },
                "energy": {"$sum": "$total_energy_kWh"},
                "cost":   {"$sum": "$total_cost_EGP"},
            }},
            {"$sort": {"_id.year": 1, "_id.week": 1}},
        ]
    else:
        pipeline = [
            {"$group": {
                "_id": {
                    "period": {"$dateToString": {"format": "%Y-%m", "date": {"$dateFromString": {"dateString": "$interval_start"}}}},
                    "device": "$device_name",
                },
                "energy": {"$sum": "$total_energy_kWh"},
                "cost":   {"$sum": "$total_cost_EGP"},
            }},
            {"$sort": {"_id.period": 1}},
        ]

    raw = list(data_col.aggregate(pipeline))

    # Build label list and per-device data maps
    devices = sorted(data_col.distinct("device_name"))
    label_set = []
    seen = set()

    for r in raw:
        if granularity == "weekly":
            lbl = f"{r['_id']['year']}-W{r['_id']['week']:02d}"
        else:
            lbl = r["_id"]["period"]
        if lbl not in seen:
            label_set.append(lbl)
            seen.add(lbl)

    device_energy_map = {d: {lbl: 0 for lbl in label_set} for d in devices}
    device_cost_map   = {d: {lbl: 0 for lbl in label_set} for d in devices}

    for r in raw:
        dev = r["_id"]["device"]
        lbl = f"{r['_id']['year']}-W{r['_id']['week']:02d}" if granularity == "weekly" else r["_id"]["period"]
        if dev in device_energy_map and lbl in device_energy_map[dev]:
            device_energy_map[dev][lbl] = round(r["energy"], 4)
            device_cost_map[dev][lbl]   = round(r["cost"],   2)

    energy_datasets = [
        {
            "label":           device,
            "data":            [device_energy_map[device][lbl] for lbl in label_set],
            "borderColor":     DEVICE_COLORS[i % len(DEVICE_COLORS)],
            "backgroundColor": DEVICE_COLORS[i % len(DEVICE_COLORS)] + "22",
            "tension":         0.4,
            "fill":            False,
        }
        for i, device in enumerate(devices)
    ]

    return ok({
        "granularity": granularity,
        "chart_data": {
            "labels":   label_set,
            "datasets": energy_datasets,
        },
        "chart_options_hint": {
            "type":    "line",
            "x_label": "Period",
            "y_label": "Energy (kWh)",
            "title":   f"Energy Consumption — {granularity.title()} View",
        },
    })


# ═══════════════════════════════════════════════════════════════════════════════
# /api/ui/charts/cost-breakdown
# Horizontal bar chart — cost and energy per device with share percentages.
# ═══════════════════════════════════════════════════════════════════════════════

@ui_bp.route("/api/ui/charts/cost-breakdown", methods=["GET"])
def ui_cost_breakdown():
    """
    Returns data shaped for a horizontal bar chart comparing cost across devices.

    Example frontend usage (Chart.js):
      new Chart(ctx, { type: 'bar', data: response.data.chart_data,
                       options: { indexAxis: 'y' } })
    """
    raw = list(data_col.aggregate([
        {"$group": {
            "_id":            "$device_name",
            "total_cost":     {"$sum": "$total_cost_EGP"},
            "total_energy":   {"$sum": "$total_energy_kWh"},
            "avg_power":      {"$avg": "$avg_power_W"},
        }},
        {"$sort": {"total_cost": -1}},
    ]))

    grand_cost = sum(r["total_cost"] for r in raw) or 1

    labels   = [r["_id"] for r in raw]
    costs    = [round(r["total_cost"],   2) for r in raw]
    energies = [round(r["total_energy"], 4) for r in raw]
    shares   = [round(r["total_cost"] / grand_cost * 100, 1) for r in raw]
    colors   = DEVICE_COLORS[:len(raw)]

    return ok({
        "chart_data": {
            "labels": labels,
            "datasets": [
                {
                    "label":           "Cost (EGP)",
                    "data":            costs,
                    "backgroundColor": colors,
                    "borderRadius":    6,
                    "yAxisID":         "y",
                },
                {
                    "label":           "Energy (kWh)",
                    "data":            energies,
                    "backgroundColor": [c + "88" for c in colors],
                    "borderRadius":    6,
                    "yAxisID":         "y1",
                },
            ],
        },
        "chart_options_hint": {
            "type":       "bar",
            "indexAxis":  "y",
            "title":      "Cost & Energy Breakdown per Appliance",
            "y_label":    "Appliance",
            "y1_label":   "Energy (kWh)",
        },
        # Table-friendly flat list for a data table alongside the chart
        "table_data": [
            {
                "rank":           i + 1,
                "device":         raw[i]["_id"],
                "cost_EGP":       costs[i],
                "energy_kWh":     energies[i],
                "share_pct":      shares[i],
                "avg_power_W":    round(raw[i]["avg_power"], 1),
                "color":          colors[i],
            }
            for i in range(len(raw))
        ],
    })


# ═══════════════════════════════════════════════════════════════════════════════
# /api/ui/anomalies/feed
# Alert panel data — paginated, with severity badges and full context.
# ═══════════════════════════════════════════════════════════════════════════════

@ui_bp.route("/api/ui/anomalies/feed", methods=["GET"])
def ui_anomaly_feed():
    """
    Query params:
      ?limit=20   ?offset=0   ?severity=critical|high|medium|low

    Returns structured alert objects ready to render as notification cards.

    Each alert includes:
      severity_badge  → { label, color, bg_color } for badge UI component
      readable_time   → human-friendly timestamp
      headline        → single-line summary string for the alert card title
    """
    limit  = min(int(request.args.get("limit",  20)), 100)
    offset = int(request.args.get("offset", 0))
    sev_filter = request.args.get("severity", "").lower() or None

    query = {}
    if sev_filter:
        if sev_filter not in SEVERITY_THRESHOLDS:
            return err(f"severity must be one of: critical, high, medium, low")
        ranges = {
            "critical": {"$lte": SEVERITY_THRESHOLDS["critical"]},
            "high":     {"$gt": SEVERITY_THRESHOLDS["critical"], "$lte": SEVERITY_THRESHOLDS["high"]},
            "medium":   {"$gt": SEVERITY_THRESHOLDS["high"],     "$lte": SEVERITY_THRESHOLDS["medium"]},
            "low":      {"$gt": SEVERITY_THRESHOLDS["medium"],   "$lte": 0},
        }
        query["anomaly_score"] = ranges[sev_filter]

    total = alerts_col.count_documents(query)
    raw   = list(
        alerts_col.find(query, {"_id": 0})
        .sort("anomaly_score", 1)
        .skip(offset)
        .limit(limit)
    )

    SEVERITY_BG = {
        "critical": "#fef2f2",
        "high":     "#fff7ed",
        "medium":   "#fefce8",
        "low":      "#eff6ff",
    }

    alerts = []
    for a in raw:
        sev = score_to_severity(a["anomaly_score"])
        gt  = a.get("ground_truth_anomaly") or "Unclassified anomaly"

        alerts.append({
            "device_name":      a["device_name"],
            "device_type":      a.get("device_type", ""),
            "interval_start":   a["interval_start"],
            "interval_end":     a.get("interval_end", ""),
            "avg_power_W":      round(a["avg_power_W"],  1),
            "max_power_W":      round(a["max_power_W"],  1),
            "total_energy_kWh": round(a["total_energy_kWh"], 4),
            "total_cost_EGP":   round(a.get("total_cost_EGP", 0), 2),
            "active_minutes":   a["active_minutes"],
            "anomaly_score":    round(a["anomaly_score"], 5),
            "anomaly_type":     gt,
            "severity":         sev,
            "severity_badge": {
                "label":    sev.upper(),
                "color":    SEVERITY_COLORS[sev],
                "bg_color": SEVERITY_BG[sev],
            },
            "headline": f"{a['device_name']} — {gt.replace('_', ' ').title()} detected",
            "scored_at": a.get("scored_at", ""),
        })

    return ok({
        "total":   total,
        "offset":  offset,
        "limit":   limit,
        "alerts":  alerts,
        "severity_summary": {
            sev: alerts_col.count_documents(
                {"anomaly_score": {
                    "critical": {"$lte": -0.07},
                    "high":     {"$gt": -0.07, "$lte": -0.04},
                    "medium":   {"$gt": -0.04, "$lte": -0.015},
                    "low":      {"$gt": -0.015, "$lte": 0},
                }[sev]}
            )
            for sev in ["critical", "high", "medium", "low"]
        },
    })


# ═══════════════════════════════════════════════════════════════════════════════
# /api/ui/anomalies/heatmap
# Device × day heatmap — shows which devices had alerts on which days.
# ═══════════════════════════════════════════════════════════════════════════════

@ui_bp.route("/api/ui/anomalies/heatmap", methods=["GET"])
def ui_anomaly_heatmap():
    """
    Returns a 2D matrix: rows = devices, columns = dates, values = alert count.
    Ideal for a heatmap component (e.g. react-calendar-heatmap, ApexCharts heatmap).

    Response shape:
      data.devices   → ["Microwave", "Deep Freezer", ...]
      data.dates     → ["2026-01-01", "2026-01-02", ...]
      data.matrix    → [[0,1,0,...], [0,0,2,...], ...]   (devices × dates)
      data.series    → ApexCharts-ready series format
    """
    raw = list(alerts_col.aggregate([
        {"$group": {
            "_id": {
                "device": "$device_name",
                "date":   {"$dateToString": {"format": "%Y-%m-%d",
                            "date": {"$dateFromString": {"dateString": "$interval_start"}}}},
            },
            "count":       {"$sum": 1},
            "worst_score": {"$min": "$anomaly_score"},
        }},
        {"$sort": {"_id.date": 1}},
    ]))

    devices     = sorted(data_col.distinct("device_name"))
    date_set    = sorted({r["_id"]["date"] for r in raw})

    # Build lookup: (device, date) → count
    lookup = {}
    for r in raw:
        lookup[(r["_id"]["device"], r["_id"]["date"])] = {
            "count": r["count"],
            "worst_score": r["worst_score"],
            "severity": score_to_severity(r["worst_score"]),
        }

    # Dense matrix (devices × dates)
    matrix = [
        [lookup.get((dev, date), {}).get("count", 0) for date in date_set]
        for dev in devices
    ]

    # ApexCharts heatmap series format
    apex_series = [
        {
            "name": dev,
            "data": [
                {
                    "x":        date,
                    "y":        lookup.get((dev, date), {}).get("count", 0),
                    "severity": lookup.get((dev, date), {}).get("severity", "none"),
                }
                for date in date_set
            ]
        }
        for dev in devices
    ]

    return ok({
        "devices": devices,
        "dates":   date_set,
        "matrix":  matrix,
        "series":  apex_series,
        "chart_options_hint": {
            "type":          "heatmap",
            "color_scale":   ["#e0e7ff", "#6366f1", "#4338ca"],
            "zero_color":    "#f8fafc",
            "title":         "Anomaly Heatmap — Device × Day",
        },
    })