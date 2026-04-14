const mqtt = require('mqtt');
const { deriveMetrics } = require('./metricsService');
const { saveRoomMetrics } = require('./influxService');

// 1. Connect to the Mosquitto broker using the URL from .env
const brokerUrl = process.env.MQTT_BROKER_URL || 'mqtt://mosquitto:1883';
const client = mqtt.connect(brokerUrl, {
  clientId: `backend_server_${Math.random().toString(16).slice(3)}`, // Random ID prevents connection collisions
  clean: true,
  connectTimeout: 4000,
  reconnectPeriod: 1000,
});

const TOPIC = 'home/gateway/data';

client.on('connect', () => {
  console.log('🔌 MQTT Service: Successfully connected to broker');
  
  // 2. Subscribe to the topic
  client.subscribe(TOPIC, (err) => {
    if (!err) {
      console.log(`📡 MQTT Service: Actively listening to [${TOPIC}]`);
    } else {
      console.error('❌ MQTT Service: Subscription error:', err);
    }
  });
});

// 3. Trigger this function every time a new message arrives
client.on('message', (topic, message) => {
  if (topic === TOPIC) {
    try {
      // The simulator sends text. We parse it into a JavaScript Object.
      const payload = JSON.parse(message.toString());
      
      console.log('\n⚡ --- New Gateway Data Received --- ⚡');
      console.log(`Timestamp: ${payload.timestamp}`);
      
      // Extract and print the specific wattages for your rooms
      if (payload.nodes) {
        // Calculate metrics for the Laundry room
        const laundryWatts = payload.nodes.laundry?.wattage || 0;
        const laundryMetrics = deriveMetrics(laundryWatts);

        console.log(`\n👕 Laundry Room Status:`);
        console.log(`Power:   ${laundryWatts}W`);
        console.log(`Current: ${laundryMetrics.current}A at ${laundryMetrics.voltage}V`);
        console.log(`Energy:  ${laundryMetrics.kwh} kWh`);
        console.log(`Cost:    $${laundryMetrics.cost}`);

        // SAVE TO DATABASE
        saveRoomMetrics('laundry', laundryWatts, laundryMetrics);
      }
    } catch (error) {
      console.error('❌ MQTT Service: Failed to parse message', error);
    }
  }
});

module.exports = client;