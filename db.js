const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DATA_DIR = process.env.DATA_DIR || __dirname;
const DB_PATH  = path.join(DATA_DIR, 'stimapay.db');

fs.mkdirSync(DATA_DIR, { recursive: true });

const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');

db.exec(`
CREATE TABLE IF NOT EXISTS users (
  phone        TEXT PRIMARY KEY,
  meter_number TEXT NOT NULL,
  created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payments (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  phone               TEXT NOT NULL,
  meter_number        TEXT NOT NULL,
  amount              INTEGER NOT NULL,
  checkout_request_id TEXT,
  merchant_request_id TEXT,
  mpesa_receipt       TEXT,
  result_code         TEXT,
  result_desc         TEXT,
  status              TEXT NOT NULL DEFAULT 'PENDING',
  created_at          TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pay_checkout ON payments(checkout_request_id);
CREATE INDEX IF NOT EXISTS idx_pay_status   ON payments(status);
`);

module.exports = db;