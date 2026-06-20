const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const pool = require('../config/db');
const registry = require('../services/applianceRegistry');
const { sendOtpEmail } = require('../services/mailer');

const OTP_TTL_MS = 10 * 60 * 1000; // codes are valid for 10 minutes

const SALT_ROUNDS = 12;

const DEFAULT_GATEWAY = process.env.DEFAULT_GATEWAY_ID || 'ESP32_Main_Hub';
const SAMPLE_APPLIANCES = [
  { name: 'Kitchen Light',  node_key: 'kitchen',  room: 'Kitchen' },
  { name: 'Washing Machine', node_key: 'laundry', room: 'Laundry' },
  { name: 'Air Conditioner', node_key: 'climate', room: 'Living Room' },
];

// Default Egyptian residential tariff (mid-tier). Users can change it later in Settings.
const DEFAULT_TARIFF_RATE = 1.45;

const seedSampleAppliances = async (userId) => {
  for (const a of SAMPLE_APPLIANCES) {
    await pool.query(
      `INSERT INTO appliances (user_id, name, node_key, gateway_id, is_active, room)
       VALUES ($1, $2, $3, $4, $5, $6)`,
      [userId, a.name, a.node_key, DEFAULT_GATEWAY, true, a.room]
    );
  }
  registry.invalidate();
};

const signToken = (user) =>
  jwt.sign(
    { id: user.id, email: user.email, role: user.role },
    process.env.JWT_SECRET,
    { expiresIn: process.env.JWT_EXPIRES_IN || '7d' }
  );

// POST /api/auth/register
const register = async (req, res) => {
  const { name, email, password, tariff_rate } = req.body;

  if (!name || !email || !password) {
    return res.status(400).json({ message: 'name, email, and password are required' });
  }

  try {
    const existing = await pool.query('SELECT id FROM users WHERE email = $1', [email]);
    if (existing.rowCount > 0) {
      return res.status(409).json({ message: 'An account with that email already exists' });
    }

    const password_hash = await bcrypt.hash(password, SALT_ROUNDS);

    const result = await pool.query(
      `INSERT INTO users (name, email, password_hash, tariff_rate)
       VALUES ($1, $2, $3, $4)
       RETURNING id, name, email, role, tariff_rate, created_at`,
      [name, email, password_hash, tariff_rate ?? DEFAULT_TARIFF_RATE]
    );

    const user = result.rows[0];

    try {
      await seedSampleAppliances(user.id);
    } catch (seedErr) {
      console.error('⚠️  Sample appliance seed failed:', seedErr.message);
    }

    const token = signToken(user);

    return res.status(201).json({ token, user });
  } catch (err) {
    if (err.code === '23505') {
      return res.status(409).json({ message: 'An account with that email already exists' });
    }
    console.error('Register error:', err.message);
    return res.status(500).json({ message: 'Internal server error' });
  }
};

// POST /api/auth/login
const login = async (req, res) => {
  const { email, password } = req.body;

  if (!email || !password) {
    return res.status(400).json({ message: 'email and password are required' });
  }

  try {
    const result = await pool.query(
      'SELECT id, name, email, role, tariff_rate, password_hash FROM users WHERE email = $1',
      [email]
    );

    if (result.rowCount === 0) {
      return res.status(401).json({ message: 'Invalid credentials' });
    }

    const user = result.rows[0];
    const passwordMatch = await bcrypt.compare(password, user.password_hash);

    if (!passwordMatch) {
      return res.status(401).json({ message: 'Invalid credentials' });
    }

    const token = signToken(user);

    const { password_hash, ...safeUser } = user;
    return res.status(200).json({ token, user: safeUser });
  } catch (err) {
    console.error('Login error:', err.message);
    return res.status(500).json({ message: 'Internal server error' });
  }
};

// POST /api/auth/forgot-password
// Body: { email }  ->  emails a 6-digit code (always returns a generic 200 so
// the endpoint can't be used to discover which emails are registered).
const forgotPassword = async (req, res) => {
  const { email } = req.body;

  if (!email) {
    return res.status(400).json({ message: 'email is required' });
  }

  const genericResponse = () =>
    res.status(200).json({ message: 'If that email is registered, a reset code has been sent' });

  try {
    const result = await pool.query('SELECT id FROM users WHERE email = $1', [email]);
    if (result.rowCount === 0) {
      return genericResponse();
    }

    const code = String(Math.floor(100000 + Math.random() * 900000)); // 6 digits
    const otp_hash = await bcrypt.hash(code, SALT_ROUNDS);
    const expires = new Date(Date.now() + OTP_TTL_MS);

    await pool.query(
      'UPDATE users SET reset_otp_hash = $1, reset_otp_expires = $2 WHERE id = $3',
      [otp_hash, expires, result.rows[0].id]
    );

    await sendOtpEmail(email, code);

    return genericResponse();
  } catch (err) {
    console.error('Forgot-password error:', err.message);
    return res.status(500).json({ message: 'Internal server error' });
  }
};

// POST /api/auth/reset-password
// Body: { email, code, newPassword }
const resetPassword = async (req, res) => {
  const { email, code, newPassword } = req.body;

  if (!email || !code || !newPassword) {
    return res.status(400).json({ message: 'email, code, and newPassword are required' });
  }

  try {
    const result = await pool.query(
      'SELECT id, reset_otp_hash, reset_otp_expires FROM users WHERE email = $1',
      [email]
    );

    const user = result.rows[0];
    if (!user || !user.reset_otp_hash || !user.reset_otp_expires) {
      return res.status(400).json({ message: 'Invalid or expired code' });
    }

    if (new Date(user.reset_otp_expires).getTime() < Date.now()) {
      return res.status(400).json({ message: 'Invalid or expired code' });
    }

    const codeMatch = await bcrypt.compare(String(code), user.reset_otp_hash);
    if (!codeMatch) {
      return res.status(400).json({ message: 'Invalid or expired code' });
    }

    const password_hash = await bcrypt.hash(newPassword, SALT_ROUNDS);
    await pool.query(
      'UPDATE users SET password_hash = $1, reset_otp_hash = NULL, reset_otp_expires = NULL WHERE id = $2',
      [password_hash, user.id]
    );

    return res.status(200).json({ message: 'Password has been reset. You can now log in.' });
  } catch (err) {
    console.error('Reset-password error:', err.message);
    return res.status(500).json({ message: 'Internal server error' });
  }
};

module.exports = { register, login, forgotPassword, resetPassword };
