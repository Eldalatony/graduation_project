const mqtt = require('mqtt');
const { deriveMetrics } = require('./metricsService');
const { writeEncryptedReading, flushWrites } = require('./influxService');
const registry = require('./applianceRegistry');
const bus = require('./eventBus');

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
    payload = JSON.parse(message.toString());
  } catch (err) {
    console.error('❌ MQTT parse error:', err.message);
    return;
  }

  const { gateway_id: gatewayId, nodes, timestamp } = payload;
  if (!gatewayId || !nodes) return;

  for (const [nodeKey, node] of Object.entries(nodes)) {
    const wattage = Number(node?.wattage ?? node?.power_W ?? 0);
    const status = node?.status || (wattage > 0 ? 'active' : 'idle');

    const appliance = await registry.lookup(gatewayId, nodeKey);

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

// Publish an on/off control command for a given appliance.
const publishControl = ({ gatewayId, nodeKey, applianceId, command, issuedBy }) => {
  const topic = `home/gateway/${gatewayId}/control/${nodeKey}`;
  const body = JSON.stringify({
    command,
    appliance_id: applianceId,
    issued_by: issuedBy,
    timestamp: new Date().toISOString(),
  });
  client.publish(topic, body, { qos: 0 });
  return { topic, body };
};

module.exports = { client, publishControl };
