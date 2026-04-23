const pool = require('../config/db');

// In-memory cache of active appliances keyed by "gatewayId::nodeKey".
// Refreshed on a timer and on CRUD operations.
const cache = new Map();
let lastLoaded = 0;
const TTL_MS = 30_000;

const keyOf = (gatewayId, nodeKey) => `${gatewayId}::${nodeKey}`;

const refresh = async () => {
  try {
    const { rows } = await pool.query(
      `SELECT a.id, a.user_id, a.name, a.node_key, a.gateway_id, a.is_active,
              u.tariff_rate
         FROM appliances a
         JOIN users u ON u.id = a.user_id`
    );
    cache.clear();
    for (const row of rows) {
      cache.set(keyOf(row.gateway_id, row.node_key), row);
    }
    lastLoaded = Date.now();
  } catch (err) {
    console.error('❌ Appliance registry refresh failed:', err.message);
  }
};

const ensureFresh = async () => {
  if (Date.now() - lastLoaded > TTL_MS) {
    await refresh();
  }
};

const lookup = async (gatewayId, nodeKey) => {
  await ensureFresh();
  return cache.get(keyOf(gatewayId, nodeKey)) || null;
};

const invalidate = () => { lastLoaded = 0; };

const allCached = () => Array.from(cache.values());

module.exports = { refresh, lookup, invalidate, allCached };
