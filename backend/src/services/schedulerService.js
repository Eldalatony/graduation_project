const cron = require('node-cron');
const pool = require('../config/db');
const { publishControl } = require('./mqttService');

// Map schedule.id → cron task
const tasks = new Map();

const loadEnabledSchedules = async () => {
  const { rows } = await pool.query(
    `SELECT s.id, s.appliance_id, s.action, s.cron_expression, s.is_enabled,
            a.node_key, a.gateway_id, a.user_id
       FROM schedules s
       JOIN appliances a ON a.id = s.appliance_id
      WHERE s.is_enabled = true`
  );
  return rows;
};

const registerTask = (row) => {
  if (tasks.has(row.id)) {
    tasks.get(row.id).stop();
    tasks.delete(row.id);
  }
  if (!cron.validate(row.cron_expression)) {
    console.error(`⚠️  Invalid cron "${row.cron_expression}" for schedule ${row.id}`);
    return;
  }
  const task = cron.schedule(row.cron_expression, () => {
    const command = row.action === 'on' ? 'turn_on' : 'turn_off';
    try {
      publishControl({
        gatewayId: row.gateway_id,
        nodeKey: row.node_key,
        applianceId: row.appliance_id,
        command,
        issuedBy: `schedule:${row.id}`,
      });
      pool.query(
        `UPDATE appliances SET is_active = $1 WHERE id = $2`,
        [command === 'turn_on', row.appliance_id]
      ).catch(() => {});
      console.log(`⏰ Schedule ${row.id} fired: ${command} for appliance ${row.appliance_id}`);
    } catch (err) {
      console.error(`❌ Schedule ${row.id} error:`, err.message);
    }
  });
  tasks.set(row.id, task);
};

const reloadAll = async () => {
  for (const task of tasks.values()) task.stop();
  tasks.clear();
  const rows = await loadEnabledSchedules();
  rows.forEach(registerTask);
  console.log(`⏰ Scheduler loaded ${rows.length} active schedules`);
};

const init = async () => {
  try {
    await reloadAll();
  } catch (err) {
    console.error('❌ Scheduler init error:', err.message);
  }
};

module.exports = { init, reloadAll };
