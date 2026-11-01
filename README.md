# StimaPay (FastAPI + PostgreSQL)

StimaPay is a **FastAPI** (Python) and **PostgreSQL** application that lets a feature phone user buy prepaid KPLC power tokens over USSD and pay with M-PESA. The user dials `*384#`, registers their meter number, enters an amount, and approves an M-PESA STK Push prompt. Payment results are reconciled via the Daraja (M-PESA) API and recorded in PostgreSQL.

## What this project does

A user dials `*384#` and is greeted with the StimaPay prepaid power menu. The first time they use it, they register their KPLC meter number. After that they can:

1. Buy a token by entering an amount in Kenya Shillings.
2. Change their registered meter number.

When the user confirms a purchase, the server triggers a Daraja STK Push to their phone. They enter their M-PESA PIN and the transaction is authorised by Safaricom. A callback updates the payment record, and a background reconcile runs 45 seconds later to settle anything the callback missed.

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

Buying a token is a three-step path: `1` for the menu, then the amount (for example `1*500`), then `1*500*1` to confirm.

## API Endpoints

- `POST /ussd` — USSD callback aggregator.
- `POST /mpesa/callback` — Daraja STK Push callback.
- `GET /api/payments` — Returns the 30 most recent payments.
- `/docs` — Interactive FastAPI Swagger documentation.

## Configuration

Set environment variables in `.env`:

- `DATABASE_URL` — PostgreSQL connection string (e.g. `postgresql://user:password@localhost:5432/stimapay`)
- `MPESA_ENV` — `sandbox` (default) or `production`
- `MPESA_CONSUMER_KEY` and `MPESA_CONSUMER_SECRET` — Daraja app credentials
- `MPESA_SHORTCODE` — paybill shortcode
- `MPESA_PASSKEY` — used with the shortcode to build the STK password
- `MPESA_CALLBACK_URL` — public URL that receives the STK callback

## Run locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the FastAPI server with Uvicorn:

```bash
uvicorn main:app --reload --port 3000
```

Open the interactive API docs:

```
http://localhost:3000/docs
```
