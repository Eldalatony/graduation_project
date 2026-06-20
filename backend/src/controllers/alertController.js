const pool = require('../config/db');

const listAlerts = async (req, res) => {
  const unreadOnly = req.query.unread === 'true';
  try {
    const { rows } = await pool.query(
      `SELECT al.id, al.user_id, al.appliance_id, ap.name AS appliance_name,
              al.type, al.message, al.is_read, al.triggered_at
         FROM alerts al
         LEFT JOIN appliances ap ON ap.id = al.appliance_id
        WHERE al.user_id = $1 ${unreadOnly ? 'AND al.is_read = false' : ''}
        ORDER BY al.triggered_at DESC
        LIMIT 50`,
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
        RETURNING id, is_read`,
      [id, req.user.id]
    );
    if (rows.length === 0) return res.status(404).json({ message: 'Alert not found' });
    res.json({ alert: rows[0] });
  } catch (err) {
    console.error('Mark alert read error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const markAllRead = async (req, res) => {
  try {
    await pool.query(
      `UPDATE alerts SET is_read = true WHERE user_id = $1 AND is_read = false`,
      [req.user.id]
    );
    res.json({ message: 'All alerts marked as read' });
  } catch (err) {
    console.error('Mark all alerts read error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

module.exports = { listAlerts, markAlertRead, markAllRead };
