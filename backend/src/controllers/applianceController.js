const pool = require('../config/db');
const registry = require('../services/applianceRegistry');
const { publishControl } = require('../services/mqttService');
const { getLiveReadings } = require('../services/influxService');

const DEFAULT_GATEWAY = process.env.DEFAULT_GATEWAY_ID || 'ESP32_Main_Hub';

const listAppliances = async (req, res) => {
  try {
    const { rows } = await pool.query(
      `SELECT id, user_id, name, node_key, gateway_id, is_active, created_at
         FROM appliances
        WHERE user_id = $1
        ORDER BY created_at ASC`,
      [req.user.id]
    );
    res.json({ appliances: rows });
  } catch (err) {
    console.error('List appliances error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const createAppliance = async (req, res) => {
  const { name, node_key, gateway_id, is_active } = req.body;
  if (!name || !node_key) {
    return res.status(400).json({ message: 'name and node_key are required' });
  }
  try {
    const { rows } = await pool.query(
      `INSERT INTO appliances (user_id, name, node_key, gateway_id, is_active)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING id, user_id, name, node_key, gateway_id, is_active, created_at`,
      [req.user.id, name, node_key, gateway_id || DEFAULT_GATEWAY, is_active ?? true]
    );
    registry.invalidate();
    res.status(201).json({ appliance: rows[0] });
  } catch (err) {
    console.error('Create appliance error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const updateAppliance = async (req, res) => {
  const { id } = req.params;
  const { name, node_key, gateway_id, is_active } = req.body;
  try {
    const { rows } = await pool.query(
      `UPDATE appliances
          SET name = COALESCE($1, name),
              node_key = COALESCE($2, node_key),
              gateway_id = COALESCE($3, gateway_id),
              is_active = COALESCE($4, is_active)
        WHERE id = $5 AND user_id = $6
        RETURNING id, user_id, name, node_key, gateway_id, is_active, created_at`,
      [name, node_key, gateway_id, is_active, id, req.user.id]
    );
    if (rows.length === 0) return res.status(404).json({ message: 'Appliance not found' });
    registry.invalidate();
    res.json({ appliance: rows[0] });
  } catch (err) {
    console.error('Update appliance error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const deleteAppliance = async (req, res) => {
  const { id } = req.params;
  try {
    const { rowCount } = await pool.query(
      `DELETE FROM appliances WHERE id = $1 AND user_id = $2`,
      [id, req.user.id]
    );
    if (rowCount === 0) return res.status(404).json({ message: 'Appliance not found' });
    registry.invalidate();
    res.json({ message: 'Appliance deleted' });
  } catch (err) {
    console.error('Delete appliance error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const ownsAppliance = async (userId, applianceId) => {
  const { rows } = await pool.query(
    `SELECT id, user_id, name, node_key, gateway_id, is_active
       FROM appliances WHERE id = $1 AND user_id = $2`,
    [applianceId, userId]
  );
  return rows[0] || null;
};

const controlAppliance = async (req, res) => {
  const { id } = req.params;
  const { command } = req.body;
  if (!['on', 'off', 'turn_on', 'turn_off'].includes(command)) {
    return res.status(400).json({ message: "command must be 'on' or 'off'" });
  }
  const normalized = command === 'on' ? 'turn_on' : command === 'off' ? 'turn_off' : command;

  try {
    const appliance = await ownsAppliance(req.user.id, id);
    if (!appliance) return res.status(404).json({ message: 'Appliance not found' });

    const published = publishControl({
      gatewayId: appliance.gateway_id,
      nodeKey: appliance.node_key,
      applianceId: appliance.id,
      command: normalized,
      issuedBy: req.user.id,
    });

    await pool.query(
      `UPDATE appliances SET is_active = $1 WHERE id = $2`,
      [normalized === 'turn_on', id]
    );
    registry.invalidate();

    res.json({ message: 'Control command published', command: normalized, mqtt: published });
  } catch (err) {
    console.error('Control appliance error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const getReadings = async (req, res) => {
  const { id } = req.params;
  const minutes = Math.min(Number(req.query.minutes) || 5, 60);
  try {
    const appliance = await ownsAppliance(req.user.id, id);
    if (!appliance) return res.status(404).json({ message: 'Appliance not found' });

    const readings = await getLiveReadings(id, minutes);
    res.json({ appliance_id: id, minutes, readings });
  } catch (err) {
    console.error('Get readings error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

module.exports = {
  listAppliances,
  createAppliance,
  updateAppliance,
  deleteAppliance,
  controlAppliance,
  getReadings,
};
