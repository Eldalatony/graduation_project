const mqtt = require('mqtt');
const crypto = require('crypto');
const { deriveMetrics } = require('./metricsService');
const { writeEncryptedReading, flushWrites } = require('./influxService');
const registry = require('./applianceRegistry');
const bus = require('./eventBus');

const aesKeyHex = process.env.MQTT_AES_KEY;
const aesKey = aesKeyHex ? Buffer.from(aesKeyHex, 'hex') : null;
if (!aesKey || aesKey.length !== 32) {
  console.error('❌ MQTT: MQTT_AES_KEY must be 64 hex chars (32 bytes); encrypted readings will be dropped');
}

const decryptPayload = (message) => {
  if (!aesKey || aesKey.length !== 32) return null;
  const combined = Buffer.from(message.toString(), 'base64');
  if (combined.length <= 16 || (combined.length - 16) % 16 !== 0) return null;

  const iv = combined.subarray(0, 16);
  const ciphertext = combined.subarray(16);

  const decipher = crypto.createDecipheriv('aes-256-cbc', aesKey, iv);
  decipher.setAutoPadding(true);
  const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
  return decrypted.toString('utf8');
};

const parsePayload = (message) => {
  const raw = message.toString().trim();
  if (raw.startsWith('{')) {
    return JSON.parse(raw);
  }
  const plaintext = decryptPayload(message);
  if (!plaintext) return null;
  return JSON.parse(plaintext);
};

const brokerUrl = process.env.MQTT_BROKER_URL || 'mqtt://mosquitto:1883';
const clientId = `${process.env.MQTT_CLIENT_ID || 'backend_server'}_${Math.random().toString(16).slice(2, 8)}`;

const client = mqtt.connect(brokerUrl, {
  clientId,
  clean: true,
  connectTimeout: 4000,
  reconnectPeriod: 1000,
  username: process.env.MQTT_USERNAME,
  password: process.env.MQTT_PASSWORD,
  rejectUnauthorized: true,
});

const DATA_TOPIC = 'home/gateway/data';

client.on('connect', () => {
  console.log('🔌 MQTT Service: connected to broker');
  client.subscribe(DATA_TOPIC, (err) => {
    if (err) console.error('❌ MQTT subscribe error:', err.message);
    else console.log(`📡 MQTT Service: subscribed to [${DATA_TOPIC}]`);
  });
});

client.on('error', (err) => console.error('❌ MQTT error:', err.message));
client.on('reconnect', () => console.log('🔄 MQTT reconnecting...'));

client.on('message', async (topic, message) => {
  if (topic !== DATA_TOPIC) return;

  let payload;
  try {
    payload = parsePayload(message);
  } catch (err) {
    console.error('❌ MQTT payload error:', err.message);
    return;
  }
  if (!payload) {
    console.error('❌ MQTT: could not decode message (bad key or malformed payload)');
    return;
  }

  const { gateway_id: gatewayId, nodes, timestamp } = payload;
  if (!gatewayId || !nodes) return;

  for (const [nodeKey, node] of Object.entries(nodes)) {
    const appliance = await registry.lookup(gatewayId, nodeKey);

    const off = appliance && !appliance.is_active;
    const wattage = off ? 0 : Number(node?.wattage ?? node?.power_W ?? 0);
    const status = off ? 'idle' : (node?.status || (wattage > 0 ? 'active' : 'idle'));

    const metrics = deriveMetrics(wattage, appliance?.tariff_rate);
    if (!metrics) continue;

    const reading = {
      userId: appliance?.user_id || null,
      applianceId: appliance?.id || null,
      applianceName: appliance?.name || nodeKey,
      gatewayId,
      nodeKey,
      timestamp,
      powerW: wattage,
      currentA: metrics.current,
      voltageV: metrics.voltage,
      energyKwh: metrics.kwh,
      costEgp: metrics.cost,
      status,
    };

    if (appliance) {
      writeEncryptedReading(reading);
    }

    bus.emit('reading', reading);
  }

  flushWrites();
});

const encryptCommand = (plaintext) => {
  if (!aesKey || aesKey.length !== 32) return null;
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv('aes-256-cbc', aesKey, iv);
  cipher.setAutoPadding(true);
  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  return Buffer.concat([iv, ciphertext]).toString('base64');
};

const CMD_TOPIC = 'home/gateway/cmd';
const LAMP_RELAY = 'RELAY2';

const RELAY_GATEWAYS = (process.env.RELAY_GATEWAY_IDS || 'esp32-01')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);
const isRelayGateway = (gatewayId) => RELAY_GATEWAYS.includes(gatewayId);

const publishControl = ({ gatewayId, nodeKey, applianceId, command, issuedBy }) => {
  if (!isRelayGateway(gatewayId)) {
    return { topic: CMD_TOPIC, published: false, relayBacked: false, skipped: 'virtual_gateway' };
  }

  const on = command === 'turn_on' || command === 'on';
  const relayCommand = `${LAMP_RELAY}_${on ? 'ON' : 'OFF'}`;

  const payload = encryptCommand(relayCommand);
  if (!payload) {
    console.error('❌ MQTT: cannot publish control — AES key missing/invalid');
    return { topic: CMD_TOPIC, relayCommand, published: false };
  }

  console.log(`🎛️  publishControl → topic=${CMD_TOPIC} cmd=${relayCommand} connected=${client.connected} payload=${payload}`);
  client.publish(CMD_TOPIC, payload, { qos: 0 }, (err) => {
    if (err) console.error('❌ MQTT publish error:', err.message);
    else console.log(`✅ MQTT command published: ${relayCommand}`);
  });
  return { topic: CMD_TOPIC, relayCommand, published: true, relayBacked: true, connected: client.connected };
};

module.exports = { client, publishControl, encryptCommand, isRelayGateway };
