const express = require('express');
const axios = require('axios');
const { protect } = require('../middleware/authMiddleware');

const router = express.Router();

const ANALYTICS_URL = process.env.ANALYTICS_SERVICE_URL || 'http://analytics:5000';
const TIMEOUT_MS = Number(process.env.ANALYTICS_TIMEOUT_MS || 60000);

router.use(protect);

router.all(/.*/, async (req, res) => {
  try {
    const upstream = await axios({
      method: req.method,
      url: `${ANALYTICS_URL}${req.originalUrl}`,
      data: ['GET', 'HEAD'].includes(req.method) ? undefined : req.body,
      timeout: TIMEOUT_MS,
      validateStatus: () => true,
      headers: { 'Content-Type': 'application/json' },
    });
    res.status(upstream.status).json(upstream.data);
  } catch (err) {
    console.error(`❌ Analytics proxy [${req.method} ${req.originalUrl}]:`, err.message);
    const code = err.code === 'ECONNABORTED' ? 504 : 502;
    res.status(code).json({
      status: 'error',
      message: code === 504 ? 'Analytics service timed out' : 'Analytics service unavailable',
    });
  }
});

module.exports = router;
