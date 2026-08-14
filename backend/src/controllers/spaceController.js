const pool = require('../config/db');
const registry = require('../services/applianceRegistry');

const clean = (s) => (s || '').trim();

const listSpaces = async (req, res) => {
  try {
    await pool.query(
      `INSERT INTO spaces (user_id, name)
       SELECT DISTINCT user_id, room
         FROM appliances
        WHERE user_id = $1 AND room IS NOT NULL AND btrim(room) <> ''
       ON CONFLICT (user_id, name) DO NOTHING`,
      [req.user.id]
    );
    const { rows } = await pool.query(
      `SELECT id, name FROM spaces WHERE user_id = $1 ORDER BY name ASC`,
      [req.user.id]
    );
    res.json({ spaces: rows });
  } catch (err) {
    console.error('List spaces error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const createSpace = async (req, res) => {
  const name = clean(req.body.name);
  if (!name) return res.status(400).json({ message: 'name is required' });
  if (name.length > 100) return res.status(400).json({ message: 'name too long' });
  try {
    const { rows } = await pool.query(
      `INSERT INTO spaces (user_id, name) VALUES ($1, $2)
       ON CONFLICT (user_id, name) DO NOTHING
       RETURNING id, name`,
      [req.user.id, name]
    );
    if (rows.length === 0) return res.status(409).json({ message: 'A space with that name already exists' });
    res.status(201).json({ space: rows[0] });
  } catch (err) {
    console.error('Create space error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  }
};

const renameSpace = async (req, res) => {
  const { id } = req.params;
  const name = clean(req.body.name);
  if (!name) return res.status(400).json({ message: 'name is required' });
  if (name.length > 100) return res.status(400).json({ message: 'name too long' });

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const cur = await client.query(
      `SELECT name FROM spaces WHERE id = $1 AND user_id = $2`,
      [id, req.user.id]
    );
    if (cur.rows.length === 0) {
      await client.query('ROLLBACK');
      return res.status(404).json({ message: 'Space not found' });
    }
    const oldName = cur.rows[0].name;

    if (oldName !== name) {
      const dup = await client.query(
        `SELECT 1 FROM spaces WHERE user_id = $1 AND name = $2 AND id <> $3`,
        [req.user.id, name, id]
      );
      if (dup.rows.length) {
        await client.query('ROLLBACK');
        return res.status(409).json({ message: 'A space with that name already exists' });
      }
      await client.query(`UPDATE spaces SET name = $1 WHERE id = $2 AND user_id = $3`, [name, id, req.user.id]);
      await client.query(`UPDATE appliances SET room = $1 WHERE room = $2 AND user_id = $3`, [name, oldName, req.user.id]);
    }

    await client.query('COMMIT');
    registry.invalidate();
    res.json({ space: { id, name } });
  } catch (err) {
    await client.query('ROLLBACK').catch(() => {});
    console.error('Rename space error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  } finally {
    client.release();
  }
};

const deleteSpace = async (req, res) => {
  const { id } = req.params;
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const cur = await client.query(
      `SELECT name FROM spaces WHERE id = $1 AND user_id = $2`,
      [id, req.user.id]
    );
    if (cur.rows.length === 0) {
      await client.query('ROLLBACK');
      return res.status(404).json({ message: 'Space not found' });
    }
    const name = cur.rows[0].name;

    await client.query(`UPDATE appliances SET room = NULL WHERE room = $1 AND user_id = $2`, [name, req.user.id]);
    await client.query(`DELETE FROM spaces WHERE id = $1 AND user_id = $2`, [id, req.user.id]);

    await client.query('COMMIT');
    registry.invalidate();
    res.json({ message: 'Space removed' });
  } catch (err) {
    await client.query('ROLLBACK').catch(() => {});
    console.error('Delete space error:', err.message);
    res.status(500).json({ message: 'Internal server error' });
  } finally {
    client.release();
  }
};

const ensureSpace = async (userId, room) => {
  const name = clean(room);
  if (!name) return;
  await pool.query(
    `INSERT INTO spaces (user_id, name) VALUES ($1, $2) ON CONFLICT (user_id, name) DO NOTHING`,
    [userId, name]
  );
};

module.exports = { listSpaces, createSpace, renameSpace, deleteSpace, ensureSpace };
