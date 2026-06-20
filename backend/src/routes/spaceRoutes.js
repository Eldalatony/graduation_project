const express = require('express');
const { protect } = require('../middleware/authMiddleware');
const {
  listSpaces,
  createSpace,
  renameSpace,
  deleteSpace,
} = require('../controllers/spaceController');

const router = express.Router();

router.use(protect);

router.get('/', listSpaces);
router.post('/', createSpace);
router.put('/:id', renameSpace);
router.delete('/:id', deleteSpace);

module.exports = router;
