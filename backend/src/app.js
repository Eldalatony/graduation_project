const express = require('express');
const mongoose = require('mongoose');
const { Client } = require('pg');
const mqtt = require('mqtt');
const { InfluxDB } = require('@influxdata/influxdb-client');

const app = express();
const PORT = process.env.PORT || 3001;

// Initialize MQTT Listener
require('./services/mqttService');

// 1. Connect to MongoDB
mongoose.connect(process.env.MONGO_URI)
  .then(() => console.log('✅ MongoDB connected successfully'))
  .catch(err => console.error('❌ MongoDB connection error:', err.message));

// 2. Connect to PostgreSQL
const pgClient = new Client({
  host: process.env.POSTGRES_HOST,
  port: process.env.POSTGRES_PORT,
  database: process.env.POSTGRES_DB,
  user: process.env.POSTGRES_USER,
  password: process.env.POSTGRES_PASSWORD,
});
pgClient.connect()
  .then(() => console.log('✅ PostgreSQL connected successfully'))
  .catch(err => console.error('❌ PostgreSQL connection error:', err.message));

// 3. Connect to MQTT Broker
const mqttClient = mqtt.connect(process.env.MQTT_BROKER_URL);
mqttClient.on('connect', () => console.log('✅ MQTT Broker connected successfully'));
mqttClient.on('error', (err) => console.error('❌ MQTT error:', err.message));

// 4. Initialize InfluxDB Client
try {
  const influx = new InfluxDB({ url: process.env.INFLUX_URL, token: process.env.INFLUX_TOKEN });
  console.log('✅ InfluxDB client initialized successfully');
} catch (err) {
  console.error('❌ InfluxDB initialization error:', err.message);
}

// Basic health check route
app.get('/', (req, res) => {
  res.send('SHEMMS Backend Skeleton is running!');
});

app.listen(PORT, () => {
  console.log(`🚀 Backend server listening on port ${PORT}`);
});