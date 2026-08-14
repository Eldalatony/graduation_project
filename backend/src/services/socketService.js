const { Server } = require('socket.io');
const jwt = require('jsonwebtoken');
const bus = require('./eventBus');

let io = null;

const buffers = new Map();

const init = (httpServer) => {
  io = new Server(httpServer, {
    cors: { origin: '*', methods: ['GET', 'POST'] },
  });

  io.use((socket, next) => {
    const token = socket.handshake.auth?.token || socket.handshake.query?.token;
    if (!token) return next(new Error('Missing auth token'));
    try {
      const decoded = jwt.verify(token, process.env.JWT_SECRET);
      socket.userId = decoded.id;
      next();
    } catch (err) {
      next(new Error('Invalid auth token'));
    }
  });

  io.on('connection', (socket) => {
    socket.join(`user:${socket.userId}`);
    console.log(`🔌 Socket.io: user ${socket.userId} connected (${socket.id})`);

    socket.on('disconnect', () => {
      console.log(`🔌 Socket.io: user ${socket.userId} disconnected`);
    });
  });

  bus.on('reading', (r) => {
    if (!r.userId) return;
    if (!buffers.has(r.userId)) buffers.set(r.userId, []);
    buffers.get(r.userId).push({
      appliance_id: r.applianceId,
      appliance_name: r.applianceName,
      node_key: r.nodeKey,
      gateway_id: r.gatewayId,
      timestamp: r.timestamp || new Date().toISOString(),
      power_W: r.powerW,
      current_A: r.currentA,
      voltage_V: r.voltageV,
      energy_kWh: r.energyKwh,
      cost_EGP: r.costEgp,
      status: r.status,
    });
  });

  bus.on('alert', (alert) => {
    if (!io || !alert.user_id) return;
    io.to(`user:${alert.user_id}`).emit('alert', alert);
  });

  setInterval(() => {
    if (!io) return;
    for (const [userId, readings] of buffers.entries()) {
      if (readings.length === 0) continue;
      io.to(`user:${userId}`).emit('readings', readings);
      buffers.set(userId, []);
    }
  }, 1000);

  console.log('🔌 Socket.io server initialized');
  return io;
};

module.exports = { init };
