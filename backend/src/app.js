require('dotenv').config();
const http = require('http');
const express = require('express');
const mongoose = require('mongoose');

const authRoutes = require('./routes/authRoutes');
const applianceRoutes = require('./routes/applianceRoutes');
const scheduleRoutes = require('./routes/scheduleRoutes');
const alertRoutes = require('./routes/alertRoutes');
const userRoutes = require('./routes/userRoutes');

const pool = require('./config/db');
const registry = require('./services/applianceRegistry');
const scheduler = require('./services/schedulerService');
const alertEngine = require('./services/alertService');
const etl = require('./services/etlService');
const socketService = require('./services/socketService');

const app = express();
const PORT = process.env.PORT || 3001;

app.use(express.json());

// Health check
app.get('/', (_req, res) => res.send('SHEMMS Backend is running'));
app.get('/health', (_req, res) => res.json({ status: 'ok', uptime_s: process.uptime() }));

// REST routes
app.use('/api/auth', authRoutes);
app.use('/api/appliances', applianceRoutes);
app.use('/api/schedules', scheduleRoutes);
app.use('/api/alerts', alertRoutes);
app.use('/api/users', userRoutes);

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
  } catch (err) {
    console.error('❌ PostgreSQL connection error:', err.message);
  }

  // Wire event listeners BEFORE starting MQTT subscription so we can't drop early messages.
  socketService.init(server);
  alertEngine.init();
  await registry.refresh();
  await scheduler.init();
  etl.init();

  // Now connect to MQTT and start ingesting.
  require('./services/mqttService');

  server.listen(PORT, () => {
    console.log(`🚀 SHEMMS backend listening on port ${PORT}`);
  });
};

bootstrap();
