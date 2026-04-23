const express = require('express');
const { protect } = require('../middleware/authMiddleware');
const { listAlerts, markAlertRead } = require('../controllers/alertController');

const router = express.Router();

router.use(protect);
router.get('/', listAlerts);
router.put('/:id/read', markAlertRead);

module.exports = router;
