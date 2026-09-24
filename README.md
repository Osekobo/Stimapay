# StimaPay

StimaPay is a Node.js and Express application that lets a feature phone user buy
prepaid KPLC power tokens over USSD and pay with M-PESA. The user dials `*384#`,
registers their meter number, enters an amount, and approves an M-PESA STK Push
prompt. Payment results are reconciled via the Daraja (M-PESA) API and recorded
in SQLite.

## What this project does

A user dials `*384#` and is greeted with the StimaPay prepaid power menu. The
first time they use it, they register their KPLC meter number. After that they
can:

1. Buy a token by entering an amount in Kenya Shillings.
2. Change their registered meter number.

When the user confirms a purchase, the server triggers a Daraja STK Push to
their phone. They enter their M-PESA PIN and the transaction is authorised by
Safaricom. A callback updates the payment record, and a background reconcile
runs 45 seconds later to settle anything the callback missed.

## USSD flow

The complete menu users see on their phone:

```
Welcome to StimaPay Prepaid Power
Enter your KPLC meter number:
```

Once registered:

```
StimaPay Prepaid Power
Meter: 99999999999
1. Buy Token
2. Change Meter Number
```

Buying a token is a three-step path: `1` for the menu, then the amount (for
example `1*500`), then `1*500*1` to confirm. Confirming triggers the M-PESA
prompt instead of completing instantly, because the money moves for real.

## Project structure

`server.js` contains the Express server, the USSD callback handler, the M-PESA
callback, and the local test API endpoints. `db.js` opens the SQLite database
and creates the tables. `mpesa.js` wraps the Daraja STK Push and query APIs.
`public/index.html` is a browser-based test console for trying the USSD flow
without a phone. `stimapay.db` is the SQLite database file created at runtime.

## How the USSD callback works

Your USSD aggregator sends a POST request to `http://YOUR_PUBLIC_URL/ussd`
every time the user presses a key. The request body contains the fields
`sessionId`, `serviceCode`, `phoneNumber`, and `text`.

The `text` field holds the complete menu path the user has entered, with each
menu level separated by an asterisk. For example, `1*500*1` means: open the Buy
Token menu, enter 500, and confirm. The application splits `text` on the
asterisk and uses the resulting parts to decide what to show next.

The server must always answer with plain text that starts with `CON` to continue
the session or `END` to finish it. Any other format is rejected by the USSD
network.

## Server endpoints

`POST /ussd` is the USSD callback aggregator. It receives the webhook and
replies with a `CON` or `END` text response.

`POST /mpesa/callback` is the Daraja STK Push callback. Safaricom POSTs the
transaction result here and the server updates the payment status.

`GET /api/payments` returns the 30 most recent payments with their status and
M-PESA receipt numbers.

## Database schema

`users` stores each phone number and its registered meter number.

`payments` stores each transaction: phone, meter number, amount, the Daraja
checkout request ID, the M-PESA receipt number, result code and description, and
the payment status (PENDING, PAID, CANCELLED, TIMEOUT, or FAILED).

Tables are created on first run and start empty.

## Configuration

`server.js` uses environment variables. `PORT` defaults to 3000. `mpesa.js`
reads the Daraja credentials and endpoints from environment variables (see
`mpesa.js` for the full list, or the `.env` file):

- `MPESA_ENV` — `sandbox` (default) or `production`
- `MPESA_CONSUMER_KEY` and `MPESA_CONSUMER_SECRET` — Daraja app credentials
- `MPESA_SHORTCODE` — paybill shortcode
- `MPESA_PASSKEY` — used with the shortcode to build the STK password
- `MPESA_CALLBACK_URL` — public URL that receives the STK callback

## Run locally

Install dependencies:

```bash
npm install
```

Start the server:

```bash
npm start
```

The server listens on port 3000 by default. You can override it with the `PORT`
environment variable.

Open the local test console:

```bash
http://localhost:3000
```

## Testing the STK Push locally

The STK Push and callback require your server to be reachable from the public
internet. Localhost alone is not reachable by Safaricom. Expose port 3000 using
a public HTTPS tunnel such as ngrok, and set `MPESA_CALLBACK_URL` to something
like:

```bash
https://YOUR_PUBLIC_URL/mpesa/callback
```

## Security notes

Keep the Daraja consumer key, consumer secret, and passkey out of version control
and any public source files. `.env` is gitignored, and never process real transactions without first verifying the credential
values and the M-PESA environment before going live.