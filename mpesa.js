require('dotenv').config();
const crypto = require('crypto');

const CONSUMER_KEY    = process.env.MPESA_CONSUMER_KEY;
const CONSUMER_SECRET = process.env.MPESA_CONSUMER_SECRET;
const SHORTCODE       = process.env.MPESA_SHORTCODE || '174379';
const PASSKEY         = process.env.MPESA_PASSKEY;
const CALLBACK_URL    = process.env.MPESA_CALLBACK_URL;
const ENV             = process.env.MPESA_ENV || 'sandbox';

const BASE = ENV === 'production'
  ? 'https://api.safaricom.co.ke'
  : 'https://sandbox.safaricom.co.ke';

(function checkConfig() {
  const missing = [];
  if (!CONSUMER_KEY)    missing.push('MPESA_CONSUMER_KEY');
  if (!CONSUMER_SECRET) missing.push('MPESA_CONSUMER_SECRET');
  if (!PASSKEY)         missing.push('MPESA_PASSKEY');
  if (!CALLBACK_URL)    missing.push('MPESA_CALLBACK_URL');
  if (missing.length) {
    console.error('[mpesa] Missing env vars:', missing.join(', '));
    console.error('[mpesa] Check that .env exists and dotenv is loaded.');
  } else {
    console.log(`[mpesa] Config OK  env=${ENV}  shortcode=${SHORTCODE}  key=${CONSUMER_KEY.slice(0, 6)}…`);
  }
})();

let cachedToken = null;
let tokenExpiry = 0;

async function getAccessToken() {
  if (cachedToken && Date.now() < tokenExpiry) return cachedToken;

  if (!CONSUMER_KEY || !CONSUMER_SECRET) {
    throw new Error('Daraja auth: missing MPESA_CONSUMER_KEY / MPESA_CONSUMER_SECRET');
  }

  const auth = Buffer.from(`${CONSUMER_KEY}:${CONSUMER_SECRET}`).toString('base64');
  const url  = `${BASE}/oauth/v1/generate?grant_type=client_credentials`;

  const res = await fetch(url, {
    method: 'GET',
    headers: {
      Authorization: `Basic ${auth}`,
      Accept: 'application/json'
    }
  });

  const raw = await res.text();

  if (!res.ok) {
    console.error(`[mpesa] Daraja auth ${res.status} body:`, raw);
    throw new Error(`Daraja auth ${res.status}: ${raw}`);
  }

  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error(`Daraja auth: non-JSON response: ${raw}`);
  }

  if (!data.access_token) {
    throw new Error(`Daraja auth: no access_token in response: ${raw}`);
  }

  cachedToken = data.access_token;
  tokenExpiry = Date.now() + (Number(data.expires_in) - 60) * 1000;
  return cachedToken;
}

function timestamp(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Africa/Nairobi',
    year:   'numeric',
    month:  '2-digit',
    day:    '2-digit',
    hour:   '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(date).reduce((acc, p) => {
    if (p.type !== 'literal') acc[p.type] = p.value;
    return acc;
  }, {});

  return `${parts.year}${parts.month}${parts.day}${parts.hour}${parts.minute}${parts.second}`;
}

function buildPassword(ts) {
  return Buffer.from(`${SHORTCODE}${PASSKEY}${ts}`).toString('base64');
}

function normalizePhone(raw) {
  let p = String(raw || '').replace(/\D/g, '');
  if (p.startsWith('254')) return p;
  if (p.startsWith('0'))   return '254' + p.slice(1);
  if (p.length === 9)      return '254' + p;
  return p;
}

async function stkPush({ phone, amount, accountRef, description }) {
  if (!CALLBACK_URL) throw new Error('MPESA_CALLBACK_URL is not set');
  if (!PASSKEY)      throw new Error('MPESA_PASSKEY is not set');

  const token = await getAccessToken();
  const ts    = timestamp();
  const msisdn = normalizePhone(phone);

  const body = {
    BusinessShortCode: SHORTCODE,
    Password:          buildPassword(ts),
    Timestamp:         ts,
    TransactionType:   'CustomerPayBillOnline',
    Amount:            Math.round(Number(amount)),
    PartyA:            msisdn,
    PartyB:            SHORTCODE,
    PhoneNumber:       msisdn,
    CallBackURL:       CALLBACK_URL,
    AccountReference:  String(accountRef || 'StimaPay').slice(0, 12),
    TransactionDesc:   String(description || 'Power Token').slice(0, 13)
  };

  const res = await fetch(`${BASE}/mpesa/stkpush/v1/processrequest`, {
    method: 'POST',
    headers: {
      Authorization:  `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept:         'application/json'
    },
    body: JSON.stringify(body)
  });

  const raw = await res.text();
  let data;
  try { data = JSON.parse(raw); }
  catch { throw new Error(`STK push: non-JSON response (${res.status}): ${raw}`); }

  if (!res.ok || data.ResponseCode !== '0') {
    console.error('[mpesa] STK push failed:', JSON.stringify({
      status: res.status,
      request: { ...body, Password: '***' },
      response: data
    }, null, 2));
    throw new Error(
      data.errorMessage ||
      data.ResponseDescription ||
      `STK failed (${res.status}): ${raw}`
    );
  }

  return data;
}

async function stkQuery({ checkoutRequestId }) {
  const token = await getAccessToken();
  const ts    = timestamp();

  const body = {
    BusinessShortCode: SHORTCODE,
    Password:          buildPassword(ts),
    Timestamp:         ts,
    CheckoutRequestID: checkoutRequestId
  };

  const res = await fetch(`${BASE}/mpesa/stkpushquery/v1/query`, {
    method: 'POST',
    headers: {
      Authorization:  `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept:         'application/json'
    },
    body: JSON.stringify(body)
  });

  const raw = await res.text();
  let data;
  try { data = JSON.parse(raw); }
  catch {
    console.error('[mpesa] STK query non-JSON:', res.status, raw);
    return null;
  }

  if (!res.ok) {
    console.error('[mpesa] STK query failed:', res.status, data);
    return data;
  }
  return data;
}

module.exports = { stkPush, stkQuery, getAccessToken, timestamp, normalizePhone };