let transporter = null;

const smtpConfigured =
  process.env.SMTP_USER &&
  process.env.SMTP_PASS &&
  process.env.SMTP_PASS !== 'PASTE_YOUR_16_CHAR_APP_PASSWORD_HERE';

if (smtpConfigured) {
  const nodemailer = require('nodemailer');
  transporter = nodemailer.createTransport({
    host: process.env.SMTP_HOST || 'smtp.gmail.com',
    port: Number(process.env.SMTP_PORT || 465),
    secure: Number(process.env.SMTP_PORT || 465) === 465,
    auth: { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS },
  });

  transporter.verify((err) => {
    if (err) {
      console.error(`❌ Email (SMTP) login failed for ${process.env.SMTP_USER}: ${err.message}`);
      console.error('   → Check that SMTP_PASS is a Gmail APP PASSWORD (not your normal password) and 2-Step Verification is on.');
    } else {
      console.log(`✅ Email sending enabled via ${process.env.SMTP_HOST || 'smtp.gmail.com'} as ${process.env.SMTP_USER}`);
    }
  });
} else {
  console.log('⚠️  SMTP not configured — password reset codes will print to this console instead of being emailed.');
}

const BRAND = {
  name: 'SHEMMS',
  tagline: 'Smart Home Energy Monitor',
  accent: '#6366f1',
  bg: '#f1f5f9',
};

const buildOtpHtml = (code) => `
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:${BRAND.bg};padding:32px 0;font-family:Arial,Helvetica,sans-serif;">
    <tr><td align="center">
      <table role="presentation" width="440" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">
        <tr>
          <td style="background:${BRAND.accent};padding:24px 32px;color:#ffffff;">
            <div style="font-size:22px;font-weight:bold;letter-spacing:0.5px;">${BRAND.name}</div>
            <div style="font-size:13px;opacity:0.85;">${BRAND.tagline}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:32px;">
            <h1 style="margin:0 0 8px;font-size:18px;color:#0f172a;">Reset your password</h1>
            <p style="margin:0 0 24px;font-size:14px;color:#475569;line-height:1.5;">
              Use the code below to reset your password. It expires in 10 minutes.
            </p>
            <div style="text-align:center;background:${BRAND.bg};border:1px dashed #cbd5e1;border-radius:10px;padding:18px;margin-bottom:24px;">
              <span style="font-size:34px;font-weight:bold;letter-spacing:8px;color:${BRAND.accent};">${code}</span>
            </div>
            <p style="margin:0;font-size:12px;color:#94a3b8;line-height:1.5;">
              If you didn't request this, you can safely ignore this email — your password won't change.
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 32px;background:#f8fafc;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;">
            © ${new Date().getFullYear()} ${BRAND.name}. This is an automated message, please do not reply.
          </td>
        </tr>
      </table>
    </td></tr>
  </table>`;

const sendOtpEmail = async (to, code) => {
  const subject = `Your ${BRAND.name} password reset code`;
  const text = `Your password reset code is ${code}. It expires in 10 minutes.`;
  const html = buildOtpHtml(code);

  if (!transporter) {
    console.log(`📧 [DEV] Password reset code for ${to}: ${code} (expires in 10 min)`);
    return;
  }

  try {
    await transporter.sendMail({
      from: `${BRAND.name} <${process.env.SMTP_FROM || process.env.SMTP_USER}>`,
      to,
      subject,
      text,
      html,
    });
    console.log(`📧 Reset code emailed to ${to}`);
  } catch (err) {
    console.error(`❌ Failed to email reset code to ${to}: ${err.message}`);
    console.log(`📧 [FALLBACK] Password reset code for ${to}: ${code}`);
    throw err;
  }
};

module.exports = { sendOtpEmail };
