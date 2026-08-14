"""
app.py
------
SHEMMS Analytics service entry point.

Responsibilities:
  1. Load Flask app from src/api.py (which has all blueprints registered)
  2. Start a background scheduler that runs incremental inference every N minutes
  3. Bind to 0.0.0.0:$FLASK_PORT so Docker can route external traffic in

The actual route handlers live in:
  src/api.py                — core analytics endpoints (/api/analytics/*)
  src/api_ui_endpoints.py   — UI-shaped endpoints (/api/ui/*)
  src/he_layer.py           — homomorphic encryption demo (/api/he/*)
"""

import os
import sys
import logging

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("analytics.bootstrap")

from api import app

INFER_INTERVAL_MIN = int(os.environ.get("INFER_INTERVAL_MIN", "30"))
INFER_ENABLED      = os.environ.get("INFER_ENABLED", "true").lower() == "true"

def _start_scheduler():
    if not INFER_ENABLED:
        log.info("Background inference disabled (INFER_ENABLED=false)")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from infer import run_inference
    except ImportError as e:
        log.warning(f"Scheduler not started — missing dependency: {e}")
        return

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        lambda: _safe_infer(run_inference),
        "interval",
        minutes=INFER_INTERVAL_MIN,
        next_run_time=None,
        id="incremental_inference",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info(f"Background inference scheduled every {INFER_INTERVAL_MIN} min")

def _safe_infer(fn):
    try:
        result = fn()
        log.info(f"Inference tick: {result}")
    except Exception as ex:
        log.error(f"Inference tick failed: {ex}")

_start_scheduler()

if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", 5000))
    log.info(f"SHEMMS Analytics API starting on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
