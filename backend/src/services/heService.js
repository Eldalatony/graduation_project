const crypto = require('crypto');

const ALGO = 'aes-256-gcm';

const getKey = () => {
  const secret = process.env.HE_SECRET || process.env.JWT_SECRET || 'shemms-dev-secret';
  return crypto.createHash('sha256').update(secret).digest();
};

const encryptNumber = (value) => {
  if (value === undefined || value === null) return null;
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv(ALGO, getKey(), iv);
  const encrypted = Buffer.concat([
    cipher.update(String(value), 'utf8'),
    cipher.final(),
  ]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, encrypted]).toString('base64');
};

const decryptNumber = (ciphertext) => {
  if (!ciphertext) return null;
  try {
    const buf = Buffer.from(ciphertext, 'base64');
    const iv = buf.subarray(0, 12);
    const tag = buf.subarray(12, 28);
    const data = buf.subarray(28);
    const decipher = crypto.createDecipheriv(ALGO, getKey(), iv);
    decipher.setAuthTag(tag);
    const decrypted = Buffer.concat([decipher.update(data), decipher.final()]);
    return Number(decrypted.toString('utf8'));
  } catch (err) {
    return null;
  }
};

module.exports = { encryptNumber, decryptNumber };
