const express = require('express');
const { protect } = require('../middleware/authMiddleware');
const {
  listAppliances,
  createAppliance,
  updateAppliance,
  deleteAppliance,
  controlAppliance,
  getReadings,
} = require('../controllers/applianceController');

const router = express.Router();

router.use(protect);

router.get('/', listAppliances);
router.post('/', createAppliance);
router.put('/:id', updateAppliance);
router.delete('/:id', deleteAppliance);
router.post('/:id/control', controlAppliance);
router.get('/:id/readings', getReadings);

module.exports = router;
