const bus = require('./eventBus');

const latest = new Map();

const init = () => {
  bus.on('reading', (r) => {
    const key = `${r.gatewayId}/${r.nodeKey}`;
    latest.set(key, {
      gateway_id: r.gatewayId,
      node_key: r.nodeKey,
      appliance_name: r.applianceName,
      receivedAt: Date.now(),
      timestamp: r.timestamp || new Date().toISOString(),
      power_W: r.powerW,
      current_A: r.currentA,
      voltage_V: r.voltageV,
      energy_kWh: r.energyKwh,
      cost_EGP: r.costEgp,
      status: r.status,
    });
  });
  console.log('📊 Live readings cache initialized');
};

const snapshot = () => Object.fromEntries(latest);

module.exports = { init, snapshot };
