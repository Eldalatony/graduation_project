const express = require('express');
const liveReadings = require('../services/liveReadings');
const { protect } = require('../middleware/authMiddleware');
const pool = require('../config/db');

const router = express.Router();

const STALE_MS = 5000;

router.get('/', protect, async (req, res) => {
  try {
    const snapshot = liveReadings.snapshot();
    const now = Date.now();

    const { rows: userAppliances } = await pool.query(
      `SELECT id, name, node_key, gateway_id, is_active
         FROM appliances
        WHERE user_id = $1`,
      [req.user.id]
    );

    const result = {};

    for (const app of userAppliances) {
      const key = `${app.gateway_id}/${app.node_key}`;
      const live = snapshot[key];

      if (!app.is_active) {
        result[key] = {
          gateway_id:     app.gateway_id,
          node_key:       app.node_key,
          appliance_name: app.name,
          timestamp:      new Date().toISOString(),
          power_W:        0,
          current_A:      0,
          voltage_V:      0,
          energy_kWh:     0,
          cost_EGP:       0,
          status:         'idle',
        };
        continue;
      }

      const lastSeenMs = live?.receivedAt || 0;
      const stale = !live || (now - lastSeenMs) > STALE_MS;

      if (stale) {
        result[key] = {
          gateway_id:     app.gateway_id,
          node_key:       app.node_key,
          appliance_name: app.name,
          timestamp:      live?.timestamp || null,
          power_W:        0,
          current_A:      0,
          voltage_V:      0,
          energy_kWh:     0,
          cost_EGP:       0,
          status:         'offline',
        };
      } else {
        result[key] = { ...live, appliance_name: app.name };
      }
    }

    res.json(result);
  } catch (err) {
    console.error('Live snapshot error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
});

module.exports = router;
