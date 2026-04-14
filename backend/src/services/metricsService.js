// Grab constants from .env, or use standard defaults
const VOLTAGE = process.env.GRID_VOLTAGE || 220; 
const COST_PER_KWH = process.env.TARIFF_RATE || 1.5; // Example cost per kWh
const INTERVAL_SECONDS = 1; // Assuming your simulator sends data every 1 second

const deriveMetrics = (wattage) => {
  if (wattage === undefined || wattage === null) return null;

  // 1. Calculate Current in Amperes (I = P / V)
  const current = wattage / VOLTAGE;

  // 2. Calculate Energy in kWh for this 1-second slice
  // (Watts / 1000 = kW) * (1 second / 3600 seconds = hours)
  const kwh = (wattage / 1000) * (INTERVAL_SECONDS / 3600);

  // 3. Calculate Cost for this slice
  const cost = kwh * COST_PER_KWH;

  return {
    voltage: VOLTAGE,
    current: Number(current.toFixed(3)),
    kwh: Number(kwh.toFixed(8)), // Needs high precision since 1 second of energy is tiny
    cost: Number(cost.toFixed(8))
  };
};

module.exports = {
  deriveMetrics
};