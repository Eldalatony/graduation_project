const { EventEmitter } = require('events');

// Shared in-process event bus for live readings, control commands, alerts.
const bus = new EventEmitter();
bus.setMaxListeners(50);

module.exports = bus;
