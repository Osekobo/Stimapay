const Database = require('better-sqlite3');
const path = require('path');
const db = new Database(path.join(__dirname, 'telecom.db'));
db.pragma('journal_mode = WAL');
db.exec(`
CREATE TABLE IF NOT EXISTS bundles (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  data_mb INTEGER NOT NULL,
  price INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL,
  bundle_id INTEGER NOT NULL,
  amount INTEGER NOT NULL,
  mpesa_code TEXT,
  status TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(bundle_id) REFERENCES bundles(id)
);
CREATE TABLE IF NOT EXISTS activations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  transaction_id INTEGER NOT NULL,
  phone TEXT NOT NULL,
  bundle_name TEXT NOT NULL,
  data_mb INTEGER NOT NULL,
  activated_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(transaction_id) REFERENCES transactions(id)
);
CREATE TABLE IF NOT EXISTS sms_receipts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL,
  message TEXT NOT NULL,
  transaction_id INTEGER NOT NULL,
  sent_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(transaction_id) REFERENCES transactions(id)
);
`);
const count = db.prepare('SELECT COUNT(*) c FROM bundles').get().c;
if (!count) {
  const add = db.prepare('INSERT INTO bundles (id,name,data_mb,price) VALUES (?,?,?,?)');
  [[1,'100MB',100,10],[2,'500MB',500,50],[3,'1GB',1024,99],[4,'2GB',2048,180]].forEach(x => add.run(...x));
}
module.exports = db;
