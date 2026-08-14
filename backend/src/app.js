require('dotenv').config();
const http = require('http');
const express = require('express');
const mongoose = require('mongoose');

const authRoutes = require('./routes/authRoutes');
const applianceRoutes = require('./routes/applianceRoutes');
const spaceRoutes = require('./routes/spaceRoutes');
const scheduleRoutes = require('./routes/scheduleRoutes');
const alertRoutes = require('./routes/alertRoutes');
const userRoutes = require('./routes/userRoutes');
const analyticsRoutes = require('./routes/analyticsRoutes');
const liveRoutes = require('./routes/liveRoutes');

const pool = require('./config/db');
const registry = require('./services/applianceRegistry');
const scheduler = require('./services/schedulerService');
const alertEngine = require('./services/alertService');
const etl = require('./services/etlService');
const socketService = require('./services/socketService');
const liveReadings = require('./services/liveReadings');

const app = express();
const PORT = process.env.PORT || 3001;

app.use(express.json());

app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type,Authorization');
  if (req.method === 'OPTIONS') {
    return res.sendStatus(204);
  }
  next();
});

app.get('/', (_req, res) => res.send('SHEMMS Backend is running'));
app.get('/health', (_req, res) => res.json({ status: 'ok', uptime_s: process.uptime() }));

app.use('/api/auth', authRoutes);
app.use('/api/appliances', applianceRoutes);
app.use('/api/spaces', spaceRoutes);
app.use('/api/schedules', scheduleRoutes);
app.use('/api/alerts', alertRoutes);
app.use('/api/users', userRoutes);
app.use('/api/live', liveRoutes);

app.use('/api/analytics', analyticsRoutes);
app.use('/api/ui',        analyticsRoutes);
app.use('/api/he',        analyticsRoutes);

const server = http.createServer(app);

const bootstrap = async () => {
  try {
    await mongoose.connect(process.env.MONGO_URI);
    console.log('✅ MongoDB connected');
  } catch (err) {
    console.error('❌ MongoDB connection error:', err.message);
  }

  try {
    await pool.query('SELECT 1');
    console.log('✅ PostgreSQL connected');
    await pool.query(`ALTER TABLE appliances ADD COLUMN IF NOT EXISTS room VARCHAR(100)`);
    await pool.query(`
      CREATE TABLE IF NOT EXISTS spaces (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        name VARCHAR(100) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, name)
      )`);
    await pool.query(`ALTER TABLE schedules ALTER COLUMN cron_expression DROP NOT NULL`);
    await pool.query(`ALTER TABLE schedules ADD COLUMN IF NOT EXISTS timer_minutes INT`);
    await pool.query(`ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_otp_hash VARCHAR`);
    await pool.query(`ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_otp_expires TIMESTAMP`);
    console.log('✅ DB migrations applied');
  } catch (err) {
    console.error('❌ PostgreSQL connection error:', err.message);
  }

  socketService.init(server);
  liveReadings.init();
  alertEngine.init();
  await registry.refresh();
  await scheduler.init();
  etl.init();

  require('./services/mqttService');

  server.listen(PORT, () => {
    console.log(`🚀 SHEMMS backend listening on port ${PORT}`);
  });
};

bootstrap();
