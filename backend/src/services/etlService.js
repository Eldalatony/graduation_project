const cron = require('node-cron');
const { getAggregatesSince } = require('./influxService');
const { encryptNumber } = require('./heService');
const ApplianceHistory = require('../models/applianceHistory');
const ApplianceData = require('../models/applianceData');
const registry = require('./applianceRegistry');

const ETL_CRON = process.env.ETL_CRON || '5 * * * *'; // hourly at :05
const ETL_LOOKBACK_MIN = Number(process.env.ETL_LOOKBACK_MIN || 65);

const periodKey = (date) => {
  const d = new Date(date);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}T${String(d.getUTCHours()).padStart(2, '0')}`;
};

// "2026-04-23T14" → ["2026-04-23T14:00:00Z", "2026-04-23T15:00:00Z"]
const periodToIsoRange = (period) => {
  const start = new Date(`${period}:00:00Z`);
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  return [start.toISOString().replace(/\.\d{3}Z$/, 'Z'), end.toISOString().replace(/\.\d{3}Z$/, 'Z')];
};

const runOnce = async () => {
  const since = new Date(Date.now() - ETL_LOOKBACK_MIN * 60 * 1000).toISOString();
  let rows;
  try {
    rows = await getAggregatesSince(since);
  } catch (err) {
    console.error('❌ ETL read error:', err.message);
    return;
  }
  if (!rows.length) {
    console.log('🗄  ETL: no readings to aggregate');
    return;
  }

  // Group by (appliance_id, hour-bucket)
  const groups = new Map();
  for (const r of rows) {
    if (!r.appliance_id) continue;
    const bucket = periodKey(r.time);
    const key = `${r.appliance_id}::${bucket}`;
    if (!groups.has(key)) {
      groups.set(key, {
        appliance_id: r.appliance_id,
        user_id: r.user_id,
        period: bucket,
        samples: 0,
        energy_sum: 0,
        cost_sum: 0,
        power_values: [],
        active_count: 0,
        on_off_cycles: 0,
        last_status: null,
        hour: new Date(r.time).getUTCHours(),
      });
    }
    const g = groups.get(key);
    g.samples += 1;
    if (Number.isFinite(r.energy_kWh)) g.energy_sum += r.energy_kWh;
    if (Number.isFinite(r.cost_EGP)) g.cost_sum += r.cost_EGP;
    if (Number.isFinite(r.power_W)) g.power_values.push(r.power_W);
    if (r.status === 'active') g.active_count += 1;
    if (g.last_status && g.last_status !== r.status) g.on_off_cycles += 1;
    g.last_status = r.status;
  }

  let upserts = 0;
  let dataUpserts = 0;
  for (const g of groups.values()) {
    const avgPower = g.power_values.length
      ? g.power_values.reduce((a, b) => a + b, 0) / g.power_values.length
      : 0;
    const variance = g.power_values.length
      ? g.power_values.reduce((acc, v) => acc + (v - avgPower) ** 2, 0) / g.power_values.length
      : 0;
    const maxPower = g.power_values.length ? Math.max(...g.power_values) : 0;
    const minPower = g.power_values.length ? Math.min(...g.power_values) : 0;

    // ── Encrypted history (existing) ────────────────────────────────────────
    try {
      await ApplianceHistory.updateOne(
        { appliance_id: g.appliance_id, period: g.period, aggregation_type: 'hourly' },
        {
          $set: {
            user_id: g.user_id,
            total_energy_kWh_enc: encryptNumber(Number(g.energy_sum.toFixed(6))),
            avg_power_W_enc: encryptNumber(Number(avgPower.toFixed(3))),
            total_cost_enc: encryptNumber(Number(g.cost_sum.toFixed(6))),
            peak_hour: g.hour,
            ml_features: {
              usage_variance: Number(variance.toFixed(3)),
              on_off_cycles: g.on_off_cycles,
              samples: g.samples,
            },
          },
          $setOnInsert: { created_at: new Date() },
        },
        { upsert: true }
      );
      upserts += 1;
    } catch (err) {
      console.error('❌ ETL upsert (history) error:', err.message);
    }

    // ── Plaintext mirror for analytics service ──────────────────────────────
    // Analytics is a trusted internal service that needs raw values for ML.
    // It runs in the same Docker network and never exposes this collection
    // to clients (the backend proxy is the only public-facing path).
    try {
      const appliance = await registry.lookupById(g.appliance_id);
      if (!appliance) {
        // Appliance was removed from Postgres after the readings landed —
        // skip the plaintext write to avoid orphan documents.
        continue;
      }

      const [intervalStart, intervalEnd] = periodToIsoRange(g.period);
      const activeMinutes = g.samples > 0
        ? Math.round((g.active_count / g.samples) * 60)
        : 0;

      await ApplianceData.updateOne(
        { device_name: appliance.name, interval_start: intervalStart },
        {
          $set: {
            appliance_id:     g.appliance_id,
            user_id:          g.user_id,
            gateway_id:       appliance.gateway_id,
            node_key:         appliance.node_key,
            device_name:      appliance.name,
            device_type:      appliance.device_type || appliance.name,
            interval_end:     intervalEnd,
            avg_power_W:      Number(avgPower.toFixed(1)),
            max_power_W:      Number(maxPower.toFixed(1)),
            min_power_W:      Number(minPower.toFixed(1)),
            total_energy_kWh: Number(g.energy_sum.toFixed(4)),
            total_cost_EGP:   Number(g.cost_sum.toFixed(4)),
            active_minutes:   activeMinutes,
            idle_minutes:     Math.max(0, 60 - activeMinutes),
            status_changes:   g.on_off_cycles,
          },
          $setOnInsert: { created_at: new Date() },
        },
        { upsert: true }
      );
      dataUpserts += 1;
    } catch (err) {
      console.error('❌ ETL upsert (analytics) error:', err.message);
    }
  }
  console.log(`🗄  ETL: processed ${rows.length} rows → ${upserts} history + ${dataUpserts} analytics upserts`);
};

const init = () => {
  cron.schedule(ETL_CRON, () => { runOnce().catch(() => {}); });
  console.log(`🗄  ETL job scheduled (cron: ${ETL_CRON})`);
};

module.exports = { init, runOnce };
