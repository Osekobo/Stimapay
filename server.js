const express = require('express');
const db = require('./db');
const { stkPush, stkQuery } = require('./mpesa');

const app = express();
app.use(express.urlencoded({ extended: false }));
app.use(express.json());

const PORT            = process.env.PORT || 3000;
const MIN_AMOUNT      = 1;
const MAX_AMOUNT      = 35000;
const RECONCILE_AFTER = 45_000;

function normalizePhone(raw) {
  let p = String(raw || '').replace(/\D/g, '');
  if (p.startsWith('254')) return p;
  if (p.startsWith('0'))   return '254' + p.slice(1);
  if (p.length === 9)      return '254' + p;
  return p;
}

function classifyResult(code, desc) {
  const c = Number(code);
  if (c === 0)    return { status: 'PAID',      reason: 'Paid' };
  if (c === 1032) return { status: 'CANCELLED', reason: 'You cancelled the prompt.' };
  if (c === 1037) return { status: 'TIMEOUT',   reason: 'The prompt timed out.' };
  if (c === 1)    return { status: 'FAILED',    reason: 'Insufficient M-Pesa balance.' };
  if (c === 2001) return { status: 'FAILED',    reason: 'Wrong M-Pesa PIN.' };
  return { status: 'FAILED', reason: desc || `Error ${code}` };
}

async function ussdHandler({ phoneNumber = '', text = '' } = {}) {
  const phone = normalizePhone(phoneNumber);
  const raw   = String(text || '').trim();
  const parts = raw ? raw.split('*') : [];
  const last  = parts[parts.length - 1] || '';

  if (!phone) return 'END Phone number is required.';

  const user = db.prepare('SELECT phone, meter_number FROM users WHERE phone = ?').get(phone);

  if (!user) {
    if (parts.length === 0) {
      return 'CON Welcome to StimaPay Prepaid Power\nEnter your KPLC meter number:';
    }
    const meter = last.replace(/\D/g, '');
    if (meter.length < 6 || meter.length > 15) {
      return 'CON Invalid meter number.\nEnter your KPLC meter number:';
    }
    db.prepare('INSERT OR IGNORE INTO users (phone, meter_number) VALUES (?,?)')
      .run(phone, meter);
    return `END Meter ${meter} saved.\nDial *384# again and choose "Buy Token" to purchase.`;
  }

  if (parts.length === 0) {
    return `CON StimaPay Prepaid Power\nMeter: ${user.meter_number}\n`
         + `1. Buy Token\n2. Change Meter Number`;
  }

  if (parts[0] === '1') {
    if (parts.length === 1) return 'CON Enter amount in KSh:';

    if (parts.length === 2) {
      const amount = Number(parts[1]);
      if (!Number.isInteger(amount) || amount < MIN_AMOUNT || amount > MAX_AMOUNT) {
        return `CON Invalid amount.\nEnter amount in KSh (${MIN_AMOUNT} - ${MAX_AMOUNT}):`;
      }
      return `CON Buy KSh ${amount} of tokens for meter ${user.meter_number}?\n1. Confirm\n2. Cancel`;
    }

    if (parts.length === 3) {
      if (parts[2] !== '1') return 'END Request cancelled.';

      const amount = Number(parts[1]);
      if (!Number.isInteger(amount) || amount < MIN_AMOUNT || amount > MAX_AMOUNT) {
        return 'END Invalid amount. Please dial *384# again.';
      }

      try {
        const push = await stkPush({
          phone,
          amount,
          accountRef: user.meter_number,
          description: 'Power Token'
        });

        const row = db.prepare(`INSERT INTO payments
          (phone, meter_number, amount, checkout_request_id, merchant_request_id, status)
          VALUES (?,?,?,?,?, 'PENDING')`)
          .run(phone, user.meter_number, amount,
               push.CheckoutRequestID, push.MerchantRequestID);

        scheduleReconcile(row.lastInsertRowid, push.CheckoutRequestID);

        return `END M-Pesa prompt sent for KSh ${amount}.\n`
             + `Enter your M-Pesa PIN on your phone to complete.`;
      } catch (err) {
        console.error('STK push error:', err.message);
        return 'END Could not send the M-Pesa prompt. Please try again later.';
      }
    }

    return 'END Invalid choice. Please try again.';
  }

  if (parts[0] === '2') {
    if (parts.length === 1) {
      return `CON Current meter: ${user.meter_number}\nEnter new KPLC meter number:`;
    }
    if (parts.length === 2) {
      const newMeter = parts[1].replace(/\D/g, '');
      if (newMeter.length < 6 || newMeter.length > 15) {
        return 'CON Invalid meter number.\nEnter new KPLC meter number:';
      }
      db.prepare('UPDATE users SET meter_number = ? WHERE phone = ?')
        .run(newMeter, phone);
      return `END Meter updated to ${newMeter}.\nDial *384# again to buy tokens.`;
    }
    return 'END Invalid choice. Please try again.';
  }

  return 'END Invalid choice. Please try again.';
}

app.post('/mpesa/callback', (req, res) => {
  const cb = req.body && req.body.Body && req.body.Body.stkCallback;
  console.log('M-Pesa callback:', JSON.stringify(req.body));

  if (cb) {
    const payment = db.prepare('SELECT * FROM payments WHERE checkout_request_id = ?')
                      .get(cb.CheckoutRequestID);

    if (payment) {
      const { status, reason } = classifyResult(cb.ResultCode, cb.ResultDesc);

      let receipt = null;
      if (status === 'PAID') {
        const items = (cb.CallbackMetadata && cb.CallbackMetadata.Item) || [];
        receipt = (items.find(i => i.Name === 'MpesaReceiptNumber') || {}).Value || null;
      }

      db.prepare(`UPDATE payments
        SET status = ?, mpesa_receipt = ?, result_code = ?, result_desc = ?
        WHERE id = ?`)
        .run(status, receipt, String(cb.ResultCode), reason, payment.id);

      console.log(`Payment ${payment.id} -> ${status} (${reason})`);
    } else {
      console.warn('Callback for unknown CheckoutRequestID:', cb.CheckoutRequestID);
    }
  }

  res.json({ ResultCode: 0, ResultDesc: 'Accepted' });
});

function scheduleReconcile(paymentId, checkoutRequestId) {
  setTimeout(async () => {
    const payment = db.prepare('SELECT * FROM payments WHERE id = ?').get(paymentId);
    if (!payment || payment.status !== 'PENDING') return;

    console.log(`Reconciling payment ${paymentId} (${checkoutRequestId})...`);
    const result = await stkQuery({ checkoutRequestId });

    if (!result) {
      return;
    }

    const code = result.ResultCode ?? result.ResponseCode;
    const desc = result.ResultDesc ?? result.ResponseDescription;

    if (code === undefined || code === null) {
      console.warn('Reconcile: no result code for', checkoutRequestId, result);
      return;
    }

    if (String(code) === '500.001.1001') {
      console.log(`Payment ${paymentId} still processing, will leave as PENDING.`);
      return;
    }

    const { status, reason } = classifyResult(code, desc);
    db.prepare(`UPDATE payments
      SET status = ?, result_code = ?, result_desc = ?
      WHERE id = ?`)
      .run(status, String(code), reason, paymentId);

    console.log(`Reconcile: payment ${paymentId} -> ${status} (${reason})`);
  }, RECONCILE_AFTER);
}

app.post('/ussd', async (req, res) => {
  console.log('USSD request:', req.body);
  try {
    const response = await ussdHandler(req.body);
    res.type('text/plain').send(response);
  } catch (err) {
    console.error('USSD handler error:', err);
    res.type('text/plain').send('END Service unavailable. Please try again.');
  }
});

app.get('/api/payments', (_req, res) => {
  res.json(db.prepare(`
    SELECT id, phone, meter_number, amount, status, mpesa_receipt,
           result_code, result_desc, created_at
    FROM payments ORDER BY id DESC LIMIT 30
  `).all());
});

app.listen(PORT, () => {
  console.log(`StimaPay running on http://localhost:${PORT}`);
  console.log(`USSD callback  : POST /ussd`);
  console.log(`M-Pesa callback: POST /mpesa/callback`);
});