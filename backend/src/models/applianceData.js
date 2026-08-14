const mongoose = require('mongoose');

const applianceDataSchema = new mongoose.Schema(
  {
    appliance_id:     { type: String, required: true, index: true },
    user_id:          { type: String, required: true, index: true },
    gateway_id:       { type: String, required: true },
    node_key:         { type: String, required: true },
    device_name:      { type: String, required: true, index: true },
    device_type:      { type: String, default: 'unknown' },

    interval_start:   { type: String, required: true, index: true },
    interval_end:     { type: String, required: true },

    avg_power_W:      Number,
    max_power_W:      Number,
    min_power_W:      Number,
    total_energy_kWh: Number,
    total_cost_EGP:   Number,
    active_minutes:   Number,
    idle_minutes:     Number,
    status_changes:   Number,

    anomaly:          { type: String, default: null },

    created_at:       { type: Date, default: () => new Date() },
  },
  { collection: 'appliance_data' }
);

applianceDataSchema.index(
  { device_name: 1, interval_start: 1 },
  { unique: true }
);

module.exports = mongoose.model('ApplianceData', applianceDataSchema);
