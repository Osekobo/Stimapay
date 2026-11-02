import asyncio
import os
import random
from typing import Optional
from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from database import get_db, init_db
from mpesa import normalize_phone, stk_push, stk_query

app = FastAPI(title="M-Paya Energy USSD", version="2.1.0")

# Configure CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MIN_AMOUNT = 1
MAX_AMOUNT = 35000
RECONCILE_AFTER = 45  # seconds


@app.on_event("startup")
def startup_event():
  init_db()
  print("M-Paya Energy USSD FastAPI backend started.")


def classify_result(code, desc):
  try:
    c = int(code)
  except (TypeError, ValueError):
    return ("FAILED", desc or f"Error {code}")

  if c == 0:
    return ("PAID", "Paid")
  if c == 1032:
    return ("CANCELLED", "You cancelled the prompt.")
  if c == 1037:
    return ("TIMEOUT", "The prompt timed out.")
  if c == 1:
    return ("FAILED", "Insufficient M-Pesa balance.")
  if c == 2001:
    return ("FAILED", "Wrong M-Pesa PIN.")
  return ("FAILED", desc or f"Error {code}")


def generate_token():
  return "-".join(
      "".join(random.choices("0123456789", k=4)) for _ in range(4)
  )


def get_meter_balance(db, meter_number: str):
  base_kwh = 25.0
  paid_payments = db.execute(
      text(
          "SELECT SUM(amount) FROM payments WHERE meter_number = :m AND status"
          " = 'PAID'"
      ),
      {"m": meter_number},
  ).fetchone()
  total_paid = paid_payments[0] if (paid_payments and paid_payments[0]) else 0
  purchased_kwh = total_paid / 50.0
  total_kwh = round(base_kwh + purchased_kwh, 1)
  days_left = round(total_kwh / 4.5, 1)
  return total_kwh, days_left


def preprocess_ussd_text(text: Optional[str]) -> str:
  if not text:
    return ""
  t = str(text).strip()
  if t == "0":
    return ""
  if t.endswith("*0"):
    parts = t.split("*")
    parts = parts[:-2]
    return "*".join(parts)
  return t


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
      if not parts or parts[0] in ["1", "2", "3", "4", "5"]:
        action_desc = (
            " to check balance"
            if (parts and parts[0] == "2")
            else " to buy tokens"
            if (parts and parts[0] == "1")
            else ""
        )
        return (
            "CON Welcome to M-Paya Energy\nEnter your KPLC prepaid meter number"
            f"{action_desc}:\n0. Back"
        )
      meter = "".join(filter(str.isdigit, last))
      if len(meter) < 6 or len(meter) > 15:
        return "CON Invalid meter number.\nEnter your KPLC prepaid meter number:\n0. Back"

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
          f"END Meter {meter} successfully linked!\nDial *384# again to buy"
          " tokens or check balance."
      )

    user = {"phone": user_row[0], "meter_number": user_row[1]}

    if not parts or raw == "":
      return (
          f"CON M-Paya Energy\nMeter: {user['meter_number']}\n"
          "1. Buy Token\n"
          "2. Check Balance\n"
          "3. Report Fault\n"
          "4. Retrieve Last Token\n"
          "5. Change Meter"
      )

    choice = parts[0]

    if choice == "1":
      if len(parts) == 1:
        return "CON Enter amount in KSh (1 - 35,000):\n0. Back"

      if len(parts) == 2:
        try:
          amount = int(parts[1])
        except ValueError:
          return (
              f"CON Invalid amount.\nEnter amount in KSh ({MIN_AMOUNT} -"
              f" {MAX_AMOUNT}):\n0. Back"
          )
        if amount < MIN_AMOUNT or amount > MAX_AMOUNT:
          return (
              f"CON Invalid amount.\nEnter amount in KSh ({MIN_AMOUNT} -"
              f" {MAX_AMOUNT}):\n0. Back"
          )
        return (
            f"CON Buy KSh {amount} tokens for meter {user['meter_number']}?\n"
            "1. Confirm\n"
            "2. Cancel\n"
            "0. Back"
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

        token_str = generate_token()
        try:
          push = await stk_push(
              phone=phone,
              amount=amount,
              account_ref=user["meter_number"],
              description="Power Token",
          )
          checkout_req_id = push.get("CheckoutRequestID")
          merchant_req_id = push.get("MerchantRequestID")

          db.execute(
              text(
                  """INSERT INTO payments
                     (phone, meter_number, amount, checkout_request_id, merchant_request_id, token, status)
                     VALUES (:phone, :meter, :amount, :checkout_id, :merchant_id, :token, 'PENDING')"""
              ),
              {
                  "phone": phone,
                  "meter": user["meter_number"],
                  "amount": amount,
                  "checkout_id": checkout_req_id,
                  "merchant_id": merchant_req_id,
                  "token": token_str,
              },
          )
          db.commit()

          pay_row = db.execute(
              text(
                  "SELECT id FROM payments WHERE checkout_request_id = :cid"
              ),
              {"cid": checkout_req_id},
          ).fetchone()
          if pay_row:
            schedule_reconcile(pay_row[0], checkout_req_id)

          return (
              f"END M-Pesa prompt sent for KSh {amount}.\nEnter your PIN to"
              " complete purchase."
          )
        except Exception as err:
          print("STK push error:", err)
          return "END Could not send M-Pesa prompt. Please try again later."

      return "END Invalid choice. Please try again."

    elif choice == "2":
      if len(parts) == 1:
        kwh, days = get_meter_balance(db, user["meter_number"])
        return (
            f"END Meter: {user['meter_number']}\nBalance: {kwh} kWh\n"
            f"Est. {days} days remaining based on avg usage."
        )
      elif len(parts) >= 2:
        target_meter = "".join(filter(str.isdigit, parts[1]))
        if len(target_meter) < 6 or len(target_meter) > 15:
          return "END Invalid meter number. Please try again."

        target_exists = db.execute(
            text(
                "SELECT meter_number FROM users WHERE meter_number = :m UNION"
                " SELECT meter_number FROM payments WHERE meter_number = :m"
                " LIMIT 1"
            ),
            {"m": target_meter},
        ).fetchone()

        if not target_exists:
          return "END Invalid meter number. Please try again."

        kwh, days = get_meter_balance(db, target_meter)
        return (
            f"END Meter: {target_meter}\nBalance: {kwh} kWh\n"
            f"Est. {days} days remaining based on avg usage."
        )
      return "END Invalid choice. Please try again."

    elif choice == "3":
      if len(parts) == 1:
        return (
            "CON Select Fault Type:\n"
            "1. No Power\n"
            "2. Meter Tampered\n"
            "3. Leakage / Sparking\n"
            "0. Back"
        )
      if len(parts) == 2:
        fault_map = {"1": "No Power", "2": "Meter Tampered", "3": "Leakage"}
        fault_type = fault_map.get(last, "General Fault")

        res_ticket = db.execute(
            text(
                """INSERT INTO tickets (phone, meter_number, fault_type, status)
                   VALUES (:phone, :meter, :fault, 'OPEN')
                   RETURNING id"""
            ),
            {
                "phone": phone,
                "meter": user["meter_number"],
                "fault": fault_type,
            },
        ).fetchone()
        db.commit()
        ticket_id = res_ticket[0] if res_ticket else 1000

        return (
            f"END Fault reported successfully.\nTicket #TKT-{ticket_id}"
            f" created.\nTechnician assigned to meter {user['meter_number']}."
        )
      return "END Invalid choice."

    elif choice == "4":
      try:
        raw_phone = (
            phone.replace("254", "0", 1) if phone.startswith("254") else phone
        )
        last_pay = db.execute(
            text(
                """SELECT token, amount, mpesa_receipt, created_at
                   FROM payments
                   WHERE (phone = :phone OR phone = :raw_phone) AND meter_number = :meter AND status = 'PAID'
                   ORDER BY id DESC LIMIT 1"""
            ),
            {
                "phone": phone,
                "raw_phone": raw_phone,
                "meter": user["meter_number"],
            },
        ).fetchone()

        if not last_pay or not last_pay[0]:
          return "END No recent token found for your account."

        return (
            f"END Last Token for {user['meter_number']}:\n"
            f"Token: {last_pay[0]}\n"
            f"Amount: KSh {last_pay[1]}\n"
            f"Receipt: {last_pay[2] or 'N/A'}"
        )
      except Exception as e:
        print("Retrieve last token error:", e)
        return "END No recent token found for your account."

    elif choice == "5":
      if len(parts) == 1:
        return (
            f"CON Current meter: {user['meter_number']}\nEnter new KPLC meter"
            " number:\n0. Back"
        )
      if len(parts) == 2:
        new_meter = "".join(filter(str.isdigit, last))
        if len(new_meter) < 6 or len(new_meter) > 15:
          return "CON Invalid meter number.\nEnter new KPLC meter number:\n0. Back"
        db.execute(
            text(
                "UPDATE users SET meter_number = :meter WHERE phone = :phone"
            ),
            {"meter": new_meter, "phone": phone},
        )
        db.commit()
        return (
            f"END Meter updated to {new_meter}.\nDial *384# again to use"
            " M-Paya."
        )
      return "END Invalid choice."

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
  processed_text = preprocess_ussd_text(text)
  print(
      f"[USSD] Received -> session={sessionId}, phone={phoneNumber},"
      f" raw_text='{text}', processed_text='{processed_text}'"
  )
  try:
    response_text = await ussd_handler(
        phone_number=phoneNumber, text_input=processed_text
    )
    print(f"[USSD] Response -> {response_text.replace(chr(10), ' | ')}")
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


@app.get("/api/dashboard-data")
def get_dashboard_data():
  db = next(get_db())
  try:
    ticket_rows = db.execute(
        text(
            """SELECT id, phone, meter_number, fault_type, status, created_at
               FROM tickets ORDER BY id DESC LIMIT 50"""
        )
    ).fetchall()
    tickets = []
    for r in ticket_rows:
      tickets.append({
          "id": r[0],
          "phone": r[1],
          "meter_number": r[2],
          "fault_type": r[3],
          "status": r[4],
          "created_at": str(r[5]),
      })

    payment_rows = db.execute(
        text(
            """SELECT id, phone, meter_number, amount, mpesa_receipt, status, created_at
               FROM payments ORDER BY id DESC LIMIT 50"""
        )
    ).fetchall()
    payments = []
    for r in payment_rows:
      payments.append({
          "id": r[0],
          "phone": r[1],
          "meter_number": r[2],
          "amount": r[3],
          "mpesa_receipt": r[4],
          "status": r[5],
          "created_at": str(r[6]),
      })

    rev_row = db.execute(
        text(
            "SELECT SUM(amount) FROM payments WHERE status = 'PAID'"
        )
    ).fetchone()
    total_revenue = rev_row[0] if (rev_row and rev_row[0]) else 0

    open_row = db.execute(
        text(
            "SELECT COUNT(*) FROM tickets WHERE status = 'OPEN'"
        )
    ).fetchone()
    open_tickets = open_row[0] if (open_row and open_row[0]) else 0

    return {
        "total_revenue": total_revenue,
        "open_tickets": open_tickets,
        "tickets": tickets,
        "payments": payments,
    }
  finally:
    db.close()


@app.get("/api/payments")
def get_payments():
  db = next(get_db())
  try:
    rows = db.execute(
        text(
            """SELECT id, phone, meter_number, amount, status, mpesa_receipt,
                      token, result_code, result_desc, created_at
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
          "token": r[6],
          "result_code": r[7],
          "result_desc": r[8],
          "created_at": str(r[9]),
      })
    return payments
  finally:
    db.close()


if os.path.exists("public"):
  app.mount("/", StaticFiles(directory="public", html=True), name="public")
