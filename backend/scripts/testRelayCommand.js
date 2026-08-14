#!/usr/bin/env node
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });
const mqtt = require('mqtt');
const crypto = require('crypto');

const CMD_TOPIC = 'home/gateway/cmd';
const VALID = ['RELAY1_ON', 'RELAY1_OFF', 'RELAY2_ON', 'RELAY2_OFF'];

const command = (process.argv[2] || 'RELAY2_OFF').toUpperCase();
if (!VALID.includes(command)) {
  console.error(`❌ Invalid command "${command}". Must be one of: ${VALID.join(', ')}`);
  process.exit(1);
}

const aesKeyHex = process.env.MQTT_AES_KEY;
const aesKey = aesKeyHex ? Buffer.from(aesKeyHex, 'hex') : null;
if (!aesKey || aesKey.length !== 32) {
  console.error('❌ MQTT_AES_KEY must be 64 hex chars (32 bytes). Check backend/.env');
  process.exit(1);
}

function encryptCommand(plaintext) {
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv('aes-256-cbc', aesKey, iv);
  cipher.setAutoPadding(true);
  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  return Buffer.concat([iv, ciphertext]).toString('base64');
}

const brokerUrl = process.env.MQTT_BROKER_URL;
if (!brokerUrl) {
  console.error('❌ MQTT_BROKER_URL not set in backend/.env');
  process.exit(1);
}

console.log(`🔌 Connecting to ${brokerUrl} …`);
const client = mqtt.connect(brokerUrl, {
  clientId: `relay_tester_${Math.random().toString(16).slice(2, 8)}`,
  username: process.env.MQTT_USERNAME,
  password: process.env.MQTT_PASSWORD,
  connectTimeout: 8000,
  reconnectPeriod: 0,
});

client.on('connect', () => {
  const payload = encryptCommand(command);
  console.log(`✅ Connected. Publishing "${command}" to [${CMD_TOPIC}]`);
  console.log(`   encrypted base64: ${payload}`);
  client.publish(CMD_TOPIC, payload, { qos: 0 }, (err) => {
    if (err) {
      console.error('❌ Publish failed:', err.message);
      process.exit(1);
    }
    console.log('📤 Published. Watch the ESP serial for "[CMD] ' + command + '" and the relay/lamp.');
    client.end(() => process.exit(0));
  });
});

client.on('error', (err) => {
  console.error('❌ MQTT error:', err.message);
  process.exit(1);
});

setTimeout(() => {
  console.error('❌ Timed out connecting to the broker.');
  process.exit(1);
}, 12000);
