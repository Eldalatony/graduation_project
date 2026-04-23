const pool = require('../config/db');

const listAlerts = async (req, res) => {
  const unreadOnly = req.query.unread === 'true';
  try {
    const { rows } = await pool.query(
      `SELECT id, user_id, appliance_id, type, message, is_read, triggered_at
         FROM alerts
        WHERE user_id = $1 ${unreadOnly ? 'AND is_read = false' : ''}
        ORDER BY triggered_at DESC
        LIMIT 200`,
      [req.user.id]
    );
    res.json({ alerts: rows });
  } catch (err) {
    console.error('List alerts error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const markAlertRead = async (req, res) => {
  const { id } = req.params;
  try {
    const { rows } = await pool.query(
      `UPDATE alerts SET is_read = true
        WHERE id = $1 AND user_id = $2
        RETURNING id, user_id, appliance_id, type, message, is_read, triggered_at`,
      [id, req.user.id]
    );
    if (rows.length === 0) return res.status(404).json({ message: 'Alert not found' });
    res.json({ alert: rows[0] });
  } catch (err) {
    console.error('Mark alert read error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

module.exports = { listAlerts, markAlertRead };
