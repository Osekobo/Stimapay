# EasyTel USSD Bundle Simulator

A Node.js and Express application that simulates a USSD data bundle purchasing flow for a fictional telecom provider called EasyTel. It is designed to run against the Africa's Talking Sandbox feature phone simulator and uses SQLite for storage. This is a demo project only.

## What this project does

The application lets a feature phone user dial `*123#` and navigate a USSD menu to buy a data bundle. Because this is a sandbox demo, the entire purchase is simulated inside the application. There is no M-PESA integration, no Daraja API, no payment gateway, and no secret keys anywhere in this codebase.

A purchase is considered complete the moment the user confirms it. The server records the transaction, an activation, and a fake SMS receipt in the SQLite database, then returns the final USSD screen.

## USSD flow

The complete menu users see on their phone:

1. Buy Data Bundle
   1. 100MB for KSh 10
   2. 500MB for KSh 50
   3. 1GB for KSh 99
   4. 2GB for KSh 180
      1. Confirm purchase
      2. Cancel
2. My Data Balance
3. Last Purchase

The quick test path is to dial `1`, then `3`, then `1`, which selects the 1GB bundle, confirms the purchase, and completes the simulated activation.

## Project structure

`server.js` contains the Express server, the USSD callback handler, and the local test API endpoints. `db.js` opens the SQLite database, creates the tables, and seeds the bundle catalogue. `public/index.html` is a browser based test console for trying the USSD flow without a real phone. `telecom.db` is the SQLite database file created at runtime.

## How the USSD callback works

Africa's Talking sends a POST request to `http://YOUR_PUBLIC_URL/ussd` every time the user presses a key. The request body contains these fields: `sessionId`, `serviceCode`, `phoneNumber`, and `text`.

The `text` field is the important one. It holds the complete menu path the user has entered, with each menu level separated by an asterisk. For example, `1*3*1` means the user selected menu option 1, then bundle 3, then confirmed with option 1.

The application splits `text` on the asterisk and uses the resulting parts to decide what to show next. When there are no parts, it shows the main menu. One part of `1` shows the bundle list. Two parts show a confirmation screen. Three parts perform the simulated activation and return the final screen.

The server must always answer with plain text that starts with `CON` to continue the session or `END` to finish it. Any other format is rejected by the USSD network.

## Server endpoints

`POST /ussd` is the Africa's Talking callback. It receives the USSD webhook and replies with the `CON` or `END` text response.

`POST /api/ussd-test` is a local browser endpoint that calls the same handler and returns JSON, used by the test console.

`GET /api/bundles` returns the bundle catalogue.

`GET /api/transactions` returns the 30 most recent purchases with their receipt codes.

`GET /api/sms` returns the 30 most recent simulated SMS receipts.

## Database schema

`bundles` stores the available data bundles with their name, data allowance in megabytes, and price.

`transactions` stores each purchase with the phone number, bundle, amount, a generated receipt code, and status.

`activations` stores the simulated activation of a bundle for a phone number.

`sms_receipts` stores the simulated SMS confirmation message sent after a purchase.

The bundles table is seeded on first run with the four default bundles. The other tables start empty.

## Run locally

Install dependencies:

```bash
npm install
```

Start the server:

```bash
npm start
```

The server listens on port 3000 by default. You can override it with the `PORT` environment variable.

Open the local test console:

```bash
http://localhost:3000
```

## Africa's Talking Sandbox setup

The Africa's Talking Sandbox requires that your application is reachable from the public internet. Localhost alone is not reachable by their servers. Expose port 3000 using a public HTTPS tunnel such as ngrok, or deploy the application to a public server.

In the Africa's Talking Sandbox dashboard, create a USSD channel and set its callback URL to:

```bash
https://YOUR_PUBLIC_URL/ussd
```

Then open the Africa's Talking Simulator and test the channel using its feature phone interface.

## Security notes

This project contains no credentials, API keys, payment callbacks, or real money movement. You do not need an Africa's Talking API key to run the USSD callback, because the application only receives the USSD webhook from the Sandbox and returns the text response. Keep any Africa's Talking dashboard credentials out of the repository and out of any source files.