const express = require('express');
const { protect } = require('../middleware/authMiddleware');
const { getSettings, updateSettings } = require('../controllers/userController');

const router = express.Router();

router.use(protect);
router.get('/settings', getSettings);
router.put('/settings', updateSettings);

module.exports = router;
