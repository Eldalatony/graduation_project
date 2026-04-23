const express = require('express');
const { protect } = require('../middleware/authMiddleware');
const {
  listSchedules,
  createSchedule,
  updateSchedule,
  deleteSchedule,
} = require('../controllers/scheduleController');

const router = express.Router();

router.use(protect);
router.get('/', listSchedules);
router.post('/', createSchedule);
router.put('/:id', updateSchedule);
router.delete('/:id', deleteSchedule);

module.exports = router;
