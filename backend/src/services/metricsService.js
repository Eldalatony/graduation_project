const DEFAULT_VOLTAGE = Number(process.env.DEFAULT_VOLTAGE || 220);
const DEFAULT_TARIFF = Number(process.env.DEFAULT_TARIFF_RATE || 1.5);
const INTERVAL_SECONDS = Number(process.env.SAMPLE_INTERVAL_S || 1);

const deriveMetrics = (wattage, tariffRate) => {
  if (wattage === undefined || wattage === null) return null;

  const voltage = DEFAULT_VOLTAGE;
  const tariff = Number.isFinite(Number(tariffRate)) && Number(tariffRate) > 0
    ? Number(tariffRate)
    : DEFAULT_TARIFF;

  const current = wattage / voltage;
  const kwh = (wattage * INTERVAL_SECONDS) / 3_600_000;
  const cost = kwh * tariff;

  return {
    voltage,
    current: Number(current.toFixed(4)),
    kwh: Number(kwh.toFixed(10)),
    cost: Number(cost.toFixed(10)),
    tariff,
  };
};

module.exports = { deriveMetrics };
