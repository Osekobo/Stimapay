const express = require('express');
const crypto = require('crypto');
const db = require('./db');

const app = express();
app.use(express.urlencoded({ extended: false }));
app.use(express.json());
app.use(express.static('public'));

const PORT = process.env.PORT || 3000;

function normalizePhone(phone = '') { return String(phone).replace(/\s+/g, ''); }
function ref(prefix = 'ET') { return `${prefix}-${crypto.randomBytes(4).toString('hex').toUpperCase()}`; }
function getBundle(choice) { return db.prepare('SELECT * FROM bundles WHERE id = ?').get(Number(choice)); }

// Africa's Talking sends: sessionId, serviceCode, phoneNumber and text.
// The callback MUST respond with CON (continue) or END (finish).
function ussdHandler({ phoneNumber = '', text = '' } = {}) {
  const phone = normalizePhone(phoneNumber);
  const input = String(text || '').trim();
  const parts = input ? input.split('*') : [];

  if (!phone) return 'END Phone number is required.';

  // Main menu
  if (parts.length === 0) {
    return 'CON Welcome to EasyTel\n1. Buy Data Bundle\n2. My Data Balance\n3. Last Purchase';
  }

  // Buy bundle menu
  if (parts[0] === '1' && parts.length === 1) {
    const bundles = db.prepare('SELECT * FROM bundles ORDER BY id').all();
    return 'CON Choose a data bundle\n' + bundles
      .map(b => `${b.id}. ${b.name} - KSh ${b.price}`)
      .join('\n');
  }

  // Bundle details / confirmation
  if (parts[0] === '1' && parts.length === 2) {
    const bundle = getBundle(parts[1]);
    if (!bundle) return 'END Invalid bundle. Please try again.';
    return `CON ${bundle.name} - KSh ${bundle.price}\n1. Confirm purchase\n2. Cancel`;
  }

  // Activate bundle immediately after confirmation (simulation only).
  if (parts[0] === '1' && parts.length === 3) {
    const bundle = getBundle(parts[1]);
    if (!bundle) return 'END Invalid bundle. Please try again.';
    if (parts[2] !== '1') return 'END Purchase cancelled.';

    const receipt = ref('ET');
    const tx = db.prepare(
      'INSERT INTO transactions (phone,bundle_id,amount,mpesa_code,status) VALUES (?,?,?,?,?)'
    ).run(phone, bundle.id, bundle.price, receipt, 'COMPLETED');

    db.prepare(
      'INSERT INTO activations (transaction_id,phone,bundle_name,data_mb) VALUES (?,?,?,?)'
    ).run(tx.lastInsertRowid, phone, bundle.name, bundle.data_mb);

    const message = `EasyTel receipt ${receipt}: ${bundle.name} activated for KSh ${bundle.price}.`;
    db.prepare(
      'INSERT INTO sms_receipts (phone,message,transaction_id) VALUES (?,?,?)'
    ).run(phone, message, tx.lastInsertRowid);

    return `END Purchase successful.\n${bundle.name} activated.\nReceipt: ${receipt}`;
  }

  // Balance
  if (parts[0] === '2' && parts.length === 1) {
    const row = db.prepare(
      'SELECT COALESCE(SUM(data_mb),0) total FROM activations WHERE phone=?'
    ).get(phone);
    return `END Demo data balance: ${row.total} MB activated.`;
  }

  // Last purchase
  if (parts[0] === '3' && parts.length === 1) {
    const tx = db.prepare(
      `SELECT t.*, b.name bundle_name
       FROM transactions t
       JOIN bundles b ON b.id=t.bundle_id
       WHERE t.phone=?
       ORDER BY t.id DESC LIMIT 1`
    ).get(phone);
    return tx
      ? `END Last purchase:\n${tx.bundle_name}\nKSh ${tx.amount}\nReceipt: ${tx.mpesa_code}`
      : 'END No purchases found.';
  }

  return 'END Invalid choice. Please try again.';
}

// Africa's Talking USSD callback endpoint.
app.post('/ussd', (req, res) => {
  const response = ussdHandler(req.body);
  res.type('text/plain').send(response);
});

// Local browser test endpoint (does not call Africa's Talking).
app.post('/api/ussd-test', (req, res) => {
  res.json({ response: ussdHandler(req.body) });
});

app.get('/api/bundles', (req, res) => {
  res.json(db.prepare('SELECT id,name,price,data_mb FROM bundles ORDER BY id').all());
});

app.get('/api/transactions', (req, res) => {
  res.json(db.prepare(`
    SELECT t.id,t.phone,b.name bundle,t.amount,t.mpesa_code receipt,t.status,t.created_at
    FROM transactions t JOIN bundles b ON b.id=t.bundle_id
    ORDER BY t.id DESC LIMIT 30
  `).all());
});

app.get('/api/sms', (req, res) => {
  res.json(db.prepare('SELECT * FROM sms_receipts ORDER BY id DESC LIMIT 30').all());
});

app.listen(PORT, () => {
  console.log(`EasyTel USSD app running on http://localhost:${PORT}`);
  console.log(`Africa's Talking callback URL: /ussd`);
});
