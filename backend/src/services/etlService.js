const cron = require('node-cron');
const { getAggregatesSince } = require('./influxService');
const { encryptNumber } = require('./heService');
const ApplianceHistory = require('../models/applianceHistory');

const ETL_CRON = process.env.ETL_CRON || '5 * * * *'; // hourly at :05
const ETL_LOOKBACK_MIN = Number(process.env.ETL_LOOKBACK_MIN || 65);

const periodKey = (date) => {
  const d = new Date(date);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}T${String(d.getUTCHours()).padStart(2, '0')}`;
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
  for (const g of groups.values()) {
    const avgPower = g.power_values.length
      ? g.power_values.reduce((a, b) => a + b, 0) / g.power_values.length
      : 0;
    const variance = g.power_values.length
      ? g.power_values.reduce((acc, v) => acc + (v - avgPower) ** 2, 0) / g.power_values.length
      : 0;

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
      console.error('❌ ETL upsert error:', err.message);
    }
  }
  console.log(`🗄  ETL: processed ${rows.length} rows → ${upserts} upserts`);
};

const init = () => {
  cron.schedule(ETL_CRON, () => { runOnce().catch(() => {}); });
  console.log(`🗄  ETL job scheduled (cron: ${ETL_CRON})`);
};

module.exports = { init, runOnce };
