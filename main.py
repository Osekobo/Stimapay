import asyncio
import os
from typing import Optional
from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from database import get_db, init_db
from mpesa import normalize_phone, stk_push, stk_query

app = FastAPI(title="StimaPay", version="1.0.0")

MIN_AMOUNT = 1
MAX_AMOUNT = 35000
RECONCILE_AFTER = 45  # seconds


@app.on_event("startup")
def startup_event():
  init_db()
  print("StimaPay FastAPI backend started.")


def classify_result(code, desc):
  try:
    c = int(code)
  except (TypeError, ValueError):
    return {"status": "FAILED", "reason": desc or f"Error {code}"}

  if c == 0:
    return {"status": "PAID", "reason": "Paid"}
  if c == 1032:
    return {"status": "CANCELLED", "reason": "You cancelled the prompt."}
  if c == 1037:
    return {"status": "TIMEOUT", "reason": "The prompt timed out."}
  if c == 1:
    return {"status": "FAILED", "reason": "Insufficient M-Pesa balance."}
  if c == 2001:
    return {"status": "FAILED", "reason": "Wrong M-Pesa PIN."}
  return {"status": "FAILED", "reason": desc or f"Error {code}"}


async def ussd_handler(phone_number: str = "", text_input: str = "") -> str:
  phone = normalize_phone(phone_number)
  raw = str(text_input or "").strip()
  parts = raw.split("*") if raw else []
  last = parts[-1] if parts else ""

  if not phone:
    return "END Phone number is required."

  db = next(get_db())
  try:
    user_row = db.execute(
        text("SELECT phone, meter_number FROM users WHERE phone = :phone"),
        {"phone": phone},
    ).fetchone()

    if not user_row:
      if not parts:
        return (
            "CON Welcome to StimaPay Prepaid Power\nEnter your KPLC meter"
            " number:"
        )
      meter = "".join(filter(str.isdigit, last))
      if len(meter) < 6 or len(meter) > 15:
        return "CON Invalid meter number.\nEnter your KPLC meter number:"

      db.execute(
          text(
              "INSERT INTO users (phone, meter_number) VALUES (:phone, :meter)"
              " ON CONFLICT (phone) DO UPDATE SET meter_number ="
              " EXCLUDED.meter_number"
          ),
          {"phone": phone, "meter": meter},
      )
      db.commit()
      return (
          f"END Meter {meter} saved.\nDial *384# again and choose 'Buy Token'"
          " to purchase."
      )

    user = {"phone": user_row[0], "meter_number": user_row[1]}

    if not parts:
      return (
          f"CON StimaPay Prepaid Power\nMeter:"
          f" {user['meter_number']}\n1. Buy Token\n2. Change Meter Number"
      )

    if parts[0] == "1":
      if len(parts) == 1:
        return "CON Enter amount in KSh:"

      if len(parts) == 2:
        try:
          amount = int(parts[1])
        except ValueError:
          return (
              "CON Invalid amount.\nEnter amount in KSh"
              f" ({MIN_AMOUNT} - {MAX_AMOUNT}):"
          )
        if amount < MIN_AMOUNT or amount > MAX_AMOUNT:
          return (
              "CON Invalid amount.\nEnter amount in KSh"
              f" ({MIN_AMOUNT} - {MAX_AMOUNT}):"
          )
        return (
            f"CON Buy KSh {amount} of tokens for meter"
            f" {user['meter_number']}?\n1. Confirm\n2. Cancel"
        )

      if len(parts) == 3:
        if parts[2] != "1":
          return "END Request cancelled."

        try:
          amount = int(parts[1])
        except ValueError:
          return "END Invalid amount. Please dial *384# again."
        if amount < MIN_AMOUNT or amount > MAX_AMOUNT:
          return "END Invalid amount. Please dial *384# again."

        try:
          push = await stk_push(
              phone=phone,
              amount=amount,
              account_ref=user["meter_number"],
              description="Power Token",
          )
          checkout_req_id = push.get("CheckoutRequestID")
          merchant_req_id = push.get("MerchantRequestID")

          res_insert = db.execute(
              text(
                  """INSERT INTO payments
                     (phone, meter_number, amount, checkout_request_id, merchant_request_id, status)
                     VALUES (:phone, :meter, :amount, :checkout_id, :merchant_id, 'PENDING')
                     RETURNING id"""
              ),
              {
                  "phone": phone,
                  "meter": user["meter_number"],
                  "amount": amount,
                  "checkout_id": checkout_req_id,
                  "merchant_id": merchant_req_id,
              },
          ).fetchone()
          db.commit()

          payment_id = res_insert[0]
          schedule_reconcile(payment_id, checkout_req_id)

          return (
              f"END M-Pesa prompt sent for KSh {amount}.\nEnter your M-Pesa PIN"
              " on your phone to complete."
          )
        except Exception as err:
          print("STK push error:", err)
          return "END Could not send the M-Pesa prompt. Please try again later."

      return "END Invalid choice. Please try again."

    if parts[0] == "2":
      if len(parts) == 1:
        return (
            f"CON Current meter: {user['meter_number']}\nEnter new KPLC meter"
            " number:"
        )
      if len(parts) == 2:
        new_meter = "".join(filter(str.isdigit, last))
        if len(new_meter) < 6 or len(new_meter) > 15:
          return "CON Invalid meter number.\nEnter new KPLC meter number:"
        db.execute(
            text(
                "UPDATE users SET meter_number = :meter WHERE phone = :phone"
            ),
            {"meter": new_meter, "phone": phone},
        )
        db.commit()
        return (
            f"END Meter updated to {new_meter}.\nDial *384# again to buy"
            " tokens."
        )
      return "END Invalid choice. Please try again."

    return "END Invalid choice. Please try again."
  finally:
    db.close()


def schedule_reconcile(payment_id: int, checkout_request_id: str):
  async def reconcile_task():
    await asyncio.sleep(RECONCILE_AFTER)
    db = next(get_db())
    try:
      pay = db.execute(
          text("SELECT id, status FROM payments WHERE id = :id"),
          {"id": payment_id},
      ).fetchone()
      if not pay or pay[1] != "PENDING":
        return

      print(f"Reconciling payment {payment_id} ({checkout_request_id})...")
      result = await stk_query(checkout_request_id)
      if not result:
        return

      code = result.get("ResultCode")
      if code is None:
        code = result.get("ResponseCode")
      desc = result.get("ResultDesc")
      if desc is None:
        desc = result.get("ResponseDescription")

      if code is None:
        return

      if str(code) == "500.001.1001":
        print(f"Payment {payment_id} still processing, leaving as PENDING.")
        return

      status, reason = classify_result(code, desc)
      db.execute(
          text(
              """UPDATE payments
                 SET status = :status, result_code = :code, result_desc = :desc
                 WHERE id = :id"""
          ),
          {
              "status": status,
              "code": str(code),
              "desc": reason,
              "id": payment_id,
          },
      )
      db.commit()
      print(f"Reconcile: payment {payment_id} -> {status} ({reason})")
    except Exception as e:
      print(f"Reconcile error for payment {payment_id}: {e}")
    finally:
      db.close()

  asyncio.create_task(reconcile_task())


@app.post("/ussd/at", response_class=PlainTextResponse)
@app.post("/ussd", response_class=PlainTextResponse)
async def ussd_at_endpoint(
    sessionId: Optional[str] = Form(None),
    serviceCode: Optional[str] = Form(None),
    phoneNumber: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
):
  print(f"[USSD] Received request -> sessionId={sessionId}, phoneNumber={phoneNumber}, serviceCode={serviceCode}, text='{text}'")
  try:
    response_text = await ussd_handler(phone_number=phoneNumber, text_input=text)
    print(f"[USSD] Responding -> {response_text.replace(chr(10), ' | ')}")
    return response_text
  except Exception as err:
    print("USSD handler error:", err)
    return "END Service unavailable. Please try again."


@app.post("/mpesa/callback")
async def mpesa_callback(request: Request):
  try:
    body = await request.json()
  except Exception:
    body = {}

  print("M-Pesa callback:", body)
  cb = body.get("Body", {}).get("stkCallback")

  if cb:
    checkout_req_id = cb.get("CheckoutRequestID")
    db = next(get_db())
    try:
      payment = db.execute(
          text("SELECT id FROM payments WHERE checkout_request_id = :cid"),
          {"cid": checkout_req_id},
      ).fetchone()

      if payment:
        payment_id = payment[0]
        result_code = cb.get("ResultCode")
        result_desc = cb.get("ResultDesc")
        status, reason = classify_result(result_code, result_desc)

        receipt = None
        if status == "PAID":
          items = cb.get("CallbackMetadata", {}).get("Item", [])
          for item in items:
            if item.get("Name") == "MpesaReceiptNumber":
              receipt = item.get("Value")
              break

        db.execute(
            text(
                """UPDATE payments
                   SET status = :status, mpesa_receipt = :receipt,
                       result_code = :rcode, result_desc = :rdesc
                   WHERE id = :id"""
            ),
            {
                "status": status,
                "receipt": receipt,
                "rcode": str(result_code),
                "rdesc": reason,
                "id": payment_id,
            },
        )
        db.commit()
        print(f"Payment {payment_id} -> {status} ({reason})")
      else:
        print(
            "Callback for unknown CheckoutRequestID:"
            f" {checkout_req_id}"
        )
    finally:
      db.close()

  return {"ResultCode": 0, "ResultDesc": "Accepted"}


@app.get("/api/payments")
def get_payments():
  db = next(get_db())
  try:
    rows = db.execute(
        text(
            """SELECT id, phone, meter_number, amount, status, mpesa_receipt,
                      result_code, result_desc, created_at
               FROM payments ORDER BY id DESC LIMIT 30"""
        )
    ).fetchall()
    payments = []
    for r in rows:
      payments.append({
          "id": r[0],
          "phone": r[1],
          "meter_number": r[2],
          "amount": r[3],
          "status": r[4],
          "mpesa_receipt": r[5],
          "result_code": r[6],
          "result_desc": r[7],
          "created_at": str(r[8]),
      })
    return payments
  finally:
    db.close()


if os.path.exists("public"):
  app.mount("/", StaticFiles(directory="public", html=True), name="public")
