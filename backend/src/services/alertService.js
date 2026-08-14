const pool = require('../config/db');
const bus = require('./eventBus');
const registry = require('./applianceRegistry');

const HIGH_USAGE_THRESHOLD_W = Number(process.env.ALERT_HIGH_USAGE_W || 1500);
const LEFT_ON_DURATION_S = Number(process.env.ALERT_LEFT_ON_SECONDS || 30 * 60);
const OFFLINE_TIMEOUT_S = Number(process.env.ALERT_OFFLINE_SECONDS || 60);
const COOLDOWN_MS = Number(process.env.ALERT_COOLDOWN_MS || 5 * 60 * 1000);

const state = new Map();

const getState = (applianceId) => {
  if (!state.has(applianceId)) {
    state.set(applianceId, {
      lastSeen: 0,
      activeSince: 0,
      lastAlertAt: {},
      offlineFiredAt: 0,
    });
  }
  return state.get(applianceId);
};

const canFire = (st, type) => {
  const last = st.lastAlertAt[type] || 0;
  return Date.now() - last >= COOLDOWN_MS;
};

const persistAlert = async ({ userId, applianceId, type, message }) => {
  try {
    const { rows } = await pool.query(
      `INSERT INTO alerts (user_id, appliance_id, type, message)
       VALUES ($1, $2, $3, $4)
       RETURNING id, user_id, appliance_id, type, message, is_read, triggered_at`,
      [userId, applianceId, type, message]
    );
    bus.emit('alert', rows[0]);
    console.log(`🚨 Alert [${type}] for appliance ${applianceId}: ${message}`);
    return rows[0];
  } catch (err) {
    console.error('❌ Alert insert error:', err.message);
  }
};

const handleReading = async ({ userId, applianceId, applianceName, powerW, status }) => {
  if (!applianceId) return;
  const now = Date.now();
  const st = getState(applianceId);
  st.lastSeen = now;

  if (powerW > HIGH_USAGE_THRESHOLD_W && canFire(st, 'high_usage')) {
    st.lastAlertAt.high_usage = now;
    await persistAlert({
      userId,
      applianceId,
      type: 'high_usage',
      message: `High power detected on ${applianceName}: ${powerW.toFixed(1)}W exceeds ${HIGH_USAGE_THRESHOLD_W}W`,
    });
  }

  if (status === 'active') {
    if (!st.activeSince) st.activeSince = now;
    const durationS = (now - st.activeSince) / 1000;
    if (durationS > LEFT_ON_DURATION_S && canFire(st, 'left_on')) {
      st.lastAlertAt.left_on = now;
      await persistAlert({
        userId,
        applianceId,
        type: 'left_on',
        message: `${applianceName} has been active for over ${Math.round(durationS / 60)} minutes`,
      });
    }
  } else {
    st.activeSince = 0;
  }
};

const checkOffline = async () => {
  const now = Date.now();
  const appliances = registry.allCached();
  for (const a of appliances) {
    const st = getState(a.id);
    if (st.lastSeen === 0) continue;
    const idleS = (now - st.lastSeen) / 1000;
    if (idleS > OFFLINE_TIMEOUT_S && canFire(st, 'offline')) {
      st.lastAlertAt.offline = now;
      await persistAlert({
        userId: a.user_id,
        applianceId: a.id,
        type: 'offline',
        message: `No data received from ${a.name} for ${Math.round(idleS)}s`,
      });
    }
  }
};

const init = () => {
  bus.on('reading', (r) => { handleReading(r).catch(() => {}); });
  setInterval(() => { checkOffline().catch(() => {}); }, 30_000);
  console.log('🚨 Alert engine initialized');
};

module.exports = { init };
