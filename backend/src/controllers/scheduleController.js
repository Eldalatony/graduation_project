const cron = require('node-cron');
const pool = require('../config/db');
const scheduler = require('../services/schedulerService');

const ensureOwnsAppliance = async (userId, applianceId) => {
  const { rows } = await pool.query(
    `SELECT id FROM appliances WHERE id = $1 AND user_id = $2`,
    [applianceId, userId]
  );
  return rows.length > 0;
};

const listSchedules = async (req, res) => {
  try {
    const { rows } = await pool.query(
      `SELECT s.id, s.appliance_id, s.action, s.cron_expression, s.is_enabled, s.created_at,
              a.name AS appliance_name
         FROM schedules s
         JOIN appliances a ON a.id = s.appliance_id
        WHERE a.user_id = $1
        ORDER BY s.created_at DESC`,
      [req.user.id]
    );
    res.json({ schedules: rows });
  } catch (err) {
    console.error('List schedules error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const createSchedule = async (req, res) => {
  const { appliance_id, action, cron_expression, is_enabled } = req.body;
  if (!appliance_id || !action || !cron_expression) {
    return res.status(400).json({ message: 'appliance_id, action, and cron_expression are required' });
  }
  if (!['on', 'off'].includes(action)) {
    return res.status(400).json({ message: "action must be 'on' or 'off'" });
  }
  if (!cron.validate(cron_expression)) {
    return res.status(400).json({ message: 'invalid cron_expression' });
  }
  try {
    const owns = await ensureOwnsAppliance(req.user.id, appliance_id);
    if (!owns) return res.status(404).json({ message: 'Appliance not found' });

    const { rows } = await pool.query(
      `INSERT INTO schedules (appliance_id, action, cron_expression, is_enabled)
       VALUES ($1, $2, $3, $4)
       RETURNING id, appliance_id, action, cron_expression, is_enabled, created_at`,
      [appliance_id, action, cron_expression, is_enabled ?? true]
    );
    await scheduler.reloadAll();
    res.status(201).json({ schedule: rows[0] });
  } catch (err) {
    console.error('Create schedule error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const updateSchedule = async (req, res) => {
  const { id } = req.params;
  const { action, cron_expression, is_enabled } = req.body;
  if (action && !['on', 'off'].includes(action)) {
    return res.status(400).json({ message: "action must be 'on' or 'off'" });
  }
  if (cron_expression && !cron.validate(cron_expression)) {
    return res.status(400).json({ message: 'invalid cron_expression' });
  }
  try {
    const { rows } = await pool.query(
      `UPDATE schedules s
          SET action = COALESCE($1, s.action),
              cron_expression = COALESCE($2, s.cron_expression),
              is_enabled = COALESCE($3, s.is_enabled)
         FROM appliances a
        WHERE s.id = $4 AND s.appliance_id = a.id AND a.user_id = $5
        RETURNING s.id, s.appliance_id, s.action, s.cron_expression, s.is_enabled, s.created_at`,
      [action, cron_expression, is_enabled, id, req.user.id]
    );
    if (rows.length === 0) return res.status(404).json({ message: 'Schedule not found' });
    await scheduler.reloadAll();
    res.json({ schedule: rows[0] });
  } catch (err) {
    console.error('Update schedule error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const deleteSchedule = async (req, res) => {
  const { id } = req.params;
  try {
    const { rowCount } = await pool.query(
      `DELETE FROM schedules
        USING appliances
        WHERE schedules.id = $1
          AND schedules.appliance_id = appliances.id
          AND appliances.user_id = $2`,
      [id, req.user.id]
    );
    if (rowCount === 0) return res.status(404).json({ message: 'Schedule not found' });
    await scheduler.reloadAll();
    res.json({ message: 'Schedule deleted' });
  } catch (err) {
    console.error('Delete schedule error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

module.exports = { listSchedules, createSchedule, updateSchedule, deleteSchedule };
