const { InfluxDB, Point } = require('@influxdata/influxdb-client');
const { encryptNumber, decryptNumber } = require('./heService');

const url = process.env.INFLUXDB_URL || 'http://influxdb:8086';
const token = process.env.INFLUXDB_TOKEN;
const org = process.env.INFLUXDB_ORG || 'smart_home';
const bucket = process.env.INFLUXDB_BUCKET || 'energy_data';

const MEASUREMENT = 'appliance_readings';

const influxDB = new InfluxDB({ url, token });
const writeApi = influxDB.getWriteApi(org, bucket, 'ns');
const queryApi = influxDB.getQueryApi(org);

// Writes a single encrypted reading for an appliance.
const writeEncryptedReading = ({
  userId,
  applianceId,
  gatewayId,
  nodeKey,
  powerW,
  currentA,
  voltageV,
  energyKwh,
  costEgp,
  status,
}) => {
  const point = new Point(MEASUREMENT)
    .tag('user_id', userId || 'unknown')
    .tag('appliance_id', applianceId || 'unknown')
    .tag('gateway_id', gatewayId || 'unknown')
    .tag('node_key', nodeKey || 'unknown')
    .stringField('power_W_enc', encryptNumber(powerW) || '')
    .stringField('current_A_enc', encryptNumber(currentA) || '')
    .floatField('voltage_V', Number(voltageV) || 0)
    .stringField('energy_kWh_enc', encryptNumber(energyKwh) || '')
    .stringField('cost_EGP_enc', encryptNumber(costEgp) || '')
    .stringField('status', status || 'idle');

  writeApi.writePoint(point);
};

const flushWrites = () => writeApi.flush().catch((err) => {
  console.error('❌ InfluxDB flush error:', err.message);
});

// Read last N live readings (decrypted) for an appliance.
const getLiveReadings = async (applianceId, minutes = 5) => {
  const query = `
    from(bucket: "${bucket}")
      |> range(start: -${minutes}m)
      |> filter(fn: (r) => r._measurement == "${MEASUREMENT}")
      |> filter(fn: (r) => r.appliance_id == "${applianceId}")
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"], desc: false)
  `;
  const rows = [];
  await new Promise((resolve, reject) => {
    queryApi.queryRows(query, {
      next(row, tableMeta) {
        const obj = tableMeta.toObject(row);
        rows.push({
          time: obj._time,
          appliance_id: obj.appliance_id,
          user_id: obj.user_id,
          gateway_id: obj.gateway_id,
          node_key: obj.node_key,
          status: obj.status || null,
          voltage_V: obj.voltage_V ?? null,
          power_W: decryptNumber(obj.power_W_enc),
          current_A: decryptNumber(obj.current_A_enc),
          energy_kWh: decryptNumber(obj.energy_kWh_enc),
          cost_EGP: decryptNumber(obj.cost_EGP_enc),
        });
      },
      error(err) { reject(err); },
      complete() { resolve(); },
    });
  });
  return rows;
};

// Aggregate readings per appliance over a window (used by ETL job).
const getAggregatesSince = async (sinceIso) => {
  const query = `
    from(bucket: "${bucket}")
      |> range(start: ${sinceIso})
      |> filter(fn: (r) => r._measurement == "${MEASUREMENT}")
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  `;
  const rows = [];
  await new Promise((resolve, reject) => {
    queryApi.queryRows(query, {
      next(row, tableMeta) {
        const obj = tableMeta.toObject(row);
        rows.push({
          time: obj._time,
          user_id: obj.user_id,
          appliance_id: obj.appliance_id,
          power_W: decryptNumber(obj.power_W_enc),
          energy_kWh: decryptNumber(obj.energy_kWh_enc),
          cost_EGP: decryptNumber(obj.cost_EGP_enc),
          status: obj.status,
        });
      },
      error(err) { reject(err); },
      complete() { resolve(); },
    });
  });
  return rows;
};

module.exports = {
  writeEncryptedReading,
  flushWrites,
  getLiveReadings,
  getAggregatesSince,
};
