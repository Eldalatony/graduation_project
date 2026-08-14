const cron = require('node-cron');
const pool = require('../config/db');
const { publishControl } = require('./mqttService');
const registry = require('./applianceRegistry');

const tasks = new Map();
const timerHandles = new Map();

const executeSchedule = async (row) => {
  const command = row.action === 'on' ? 'turn_on' : 'turn_off';
  try {
    publishControl({
      gatewayId: row.gateway_id,
      nodeKey: row.node_key,
      applianceId: row.appliance_id,
      command,
      issuedBy: `schedule:${row.id}`,
    });
    await pool.query(
      `UPDATE appliances SET is_active = $1 WHERE id = $2`,
      [command === 'turn_on', row.appliance_id]
    );
    registry.invalidate();
  } catch (err) {
    console.error(`❌ Schedule ${row.id} execute error:`, err.message);
  }
};

const loadEnabledSchedules = async () => {
  const { rows } = await pool.query(
    `SELECT s.id, s.appliance_id, s.action, s.cron_expression, s.timer_minutes,
            s.is_enabled, s.created_at,
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
  const task = cron.schedule(row.cron_expression, async () => {
    await executeSchedule(row);
    console.log(`⏰ Schedule ${row.id} fired: ${row.action} for appliance ${row.appliance_id}`);
  });
  tasks.set(row.id, task);
};

const registerTimer = (row) => {
  if (timerHandles.has(row.id)) {
    clearTimeout(timerHandles.get(row.id));
    timerHandles.delete(row.id);
  }

  const fireAt = new Date(row.created_at).getTime() + row.timer_minutes * 60000;
  const delay  = fireAt - Date.now();

  if (delay <= 0) {
    pool.query(`UPDATE schedules SET is_enabled = false WHERE id = $1`, [row.id]).catch(() => {});
    return;
  }

  const handle = setTimeout(async () => {
    await executeSchedule(row);
    await pool.query(`UPDATE schedules SET is_enabled = false WHERE id = $1`, [row.id]).catch(() => {});
    timerHandles.delete(row.id);
    console.log(`⏱ Timer ${row.id} fired: ${row.action} for appliance ${row.appliance_id}`);
  }, delay);

  timerHandles.set(row.id, handle);
};

const reloadAll = async () => {
  for (const task of tasks.values()) task.stop();
  tasks.clear();
  for (const handle of timerHandles.values()) clearTimeout(handle);
  timerHandles.clear();

  const rows = await loadEnabledSchedules();
  rows.forEach(row => {
    if (row.timer_minutes != null) {
      registerTimer(row);
    } else {
      registerTask(row);
    }
  });
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
