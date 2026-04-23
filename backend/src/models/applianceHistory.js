const mongoose = require('mongoose');

const applianceHistorySchema = new mongoose.Schema(
  {
    user_id: { type: String, required: true, index: true },
    appliance_id: { type: String, required: true, index: true },
    period: { type: String, required: true }, // e.g. "2026-04-23T14"
    aggregation_type: { type: String, enum: ['hourly', 'daily'], default: 'hourly' },
    total_energy_kWh_enc: { type: String },
    avg_power_W_enc: { type: String },
    total_cost_enc: { type: String },
    peak_hour: { type: Number },
    ml_features: {
      usage_variance: Number,
      on_off_cycles: Number,
      samples: Number,
    },
    created_at: { type: Date, default: () => new Date() },
  },
  { collection: 'appliance_history' }
);

applianceHistorySchema.index({ appliance_id: 1, period: 1, aggregation_type: 1 }, { unique: true });

module.exports = mongoose.model('ApplianceHistory', applianceHistorySchema);
