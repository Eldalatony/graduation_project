const { InfluxDB, Point } = require('@influxdata/influxdb-client');

// Connect using environment variables from your .env file
const url = process.env.INFLUXDB_URL || 'http://influxdb:8086';
const token = process.env.INFLUXDB_TOKEN;
const org = process.env.INFLUXDB_ORG || 'smart_home';
const bucket = process.env.INFLUXDB_BUCKET || 'energy_data';

const influxDB = new InfluxDB({ url, token });
const writeApi = influxDB.getWriteApi(org, bucket);

// Helper function to save ALL metrics for a room
const saveRoomMetrics = (room, wattage, metrics) => {
  if (wattage === undefined || !metrics) return;

  // Create a "Point" in the time-series database
  const point = new Point('power_consumption')
    .tag('room', room)
    .floatField('wattage', wattage)
    .floatField('current', metrics.current)
    .floatField('voltage', metrics.voltage)
    .floatField('kwh', metrics.kwh)
    .floatField('cost', metrics.cost);

  writeApi.writePoint(point);
  
  // Flush saves the data immediately so it's ready for Tableau/Next.js
  writeApi.flush().then(() => {
    console.log(`💾 InfluxDB: Saved full metrics for [${room}]`);
  }).catch(err => {
    console.error('❌ InfluxDB Write Error:', err);
  });
};

module.exports = {
  saveRoomMetrics
};