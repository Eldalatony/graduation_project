const pool = require('../config/db');

const getSettings = async (req, res) => {
  try {
    const { rows } = await pool.query(
      `SELECT id, name, email, role, tariff_rate, created_at
         FROM users WHERE id = $1`,
      [req.user.id]
    );
    if (rows.length === 0) return res.status(404).json({ message: 'User not found' });
    res.json({ user: rows[0] });
  } catch (err) {
    console.error('Get settings error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const updateSettings = async (req, res) => {
  const { name, tariff_rate } = req.body;
  if (tariff_rate !== undefined && (Number.isNaN(Number(tariff_rate)) || Number(tariff_rate) < 0)) {
    return res.status(400).json({ message: 'tariff_rate must be a non-negative number' });
  }
  try {
    const { rows } = await pool.query(
      `UPDATE users
          SET name = COALESCE($1, name),
              tariff_rate = COALESCE($2, tariff_rate)
        WHERE id = $3
        RETURNING id, name, email, role, tariff_rate, created_at`,
      [name, tariff_rate, req.user.id]
    );
    res.json({ user: rows[0] });
  } catch (err) {
    console.error('Update settings error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

module.exports = { getSettings, updateSettings };
