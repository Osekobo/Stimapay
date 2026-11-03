import base64
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx
from dotenv import load_dotenv

load_dotenv()

CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
SHORTCODE = os.getenv("MPESA_SHORTCODE", "174379")
PASSKEY = os.getenv("MPESA_PASSKEY")
CALLBACK_URL = os.getenv("MPESA_CALLBACK_URL")
ENV = os.getenv("MPESA_ENV", "sandbox")

BASE = (
    "https://api.safaricom.co.ke"
    if ENV == "production"
    else "https://sandbox.safaricom.co.ke"
)

_cached_token = None
_token_expiry = 0


def check_config():
  missing = []
  if not CONSUMER_KEY:
    missing.append("MPESA_CONSUMER_KEY")
  if not CONSUMER_SECRET:
    missing.append("MPESA_CONSUMER_SECRET")
  if not PASSKEY:
    missing.append("MPESA_PASSKEY")
  if not CALLBACK_URL:
    missing.append("MPESA_CALLBACK_URL")
  if missing:
    print(f"[mpesa] Missing env vars: {', '.join(missing)}")
  else:
    key_preview = CONSUMER_KEY[:6] if CONSUMER_KEY else ""
    print(
        f"[mpesa] Config OK  env={ENV}  shortcode={SHORTCODE}"
        f"  key={key_preview}…"
    )


check_config()


async def get_access_token() -> str:
  global _cached_token, _token_expiry
  now = time.time()
  if _cached_token and now < _token_expiry:
    return _cached_token

  if not CONSUMER_KEY or not CONSUMER_SECRET:
    raise ValueError(
        "Daraja auth: missing MPESA_CONSUMER_KEY / MPESA_CONSUMER_SECRET"
    )

  auth_str = f"{CONSUMER_KEY}:{CONSUMER_SECRET}"
  auth_b64 = base64.b64encode(auth_str.encode()).decode()
  url = f"{BASE}/oauth/v1/generate?grant_type=client_credentials"

  async with httpx.AsyncClient() as client:
    res = await client.get(
        url,
        headers={"Authorization": f"Basic {auth_b64}", "Accept": "application/json"},
    )
    if res.status_code != 200:
      raise ValueError(f"Daraja auth {res.status_code}: {res.text}")

    data = res.json()
    token = data.get("access_token")
    if not token:
      raise ValueError(f"Daraja auth: no access_token in response: {res.text}")

    expires_in = float(data.get("expires_in", 3599))
    _cached_token = token
    _token_expiry = now + expires_in - 60
    return _cached_token


def get_timestamp() -> str:
  now = datetime.now(ZoneInfo("Africa/Nairobi"))
  return now.strftime("%Y%m%d%H%M%S")


def build_password(ts: str) -> str:
  raw = f"{SHORTCODE}{PASSKEY}{ts}"
  return base64.b64encode(raw.encode()).decode()


def normalize_phone(raw: str) -> str:
  s = str(raw or "").strip().replace("+", "")
  p = "".join(filter(str.isdigit, s))
  if p.startswith("254"):
    return p
  if p.startswith("0"):
    return "254" + p[1:]
  if len(p) == 9:
    return "254" + p
  return p


async def stk_push(phone: str, amount: int, account_ref: str, description: str):
  if not CALLBACK_URL:
    raise ValueError("MPESA_CALLBACK_URL is not set")
  if not PASSKEY:
    raise ValueError("MPESA_PASSKEY is not set")

  token = await get_access_token()
  ts = get_timestamp()
  msisdn = normalize_phone(phone)

  body = {
      "BusinessShortCode": SHORTCODE,
      "Password": build_password(ts),
      "Timestamp": ts,
      "TransactionType": "CustomerPayBillOnline",
      "Amount": int(amount),
      "PartyA": msisdn,
      "PartyB": SHORTCODE,
      "PhoneNumber": msisdn,
      "CallBackURL": CALLBACK_URL,
      "AccountReference": str(account_ref or "StimaPay")[:12],
      "TransactionDesc": str(description or "Power Token")[:13],
  }

  async with httpx.AsyncClient() as client:
    res = await client.post(
        f"{BASE}/mpesa/stkpush/v1/processrequest",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json=body,
    )
    data = res.json()
    if res.status_code != 200 or data.get("ResponseCode") != "0":
      print(f"[mpesa] STK push failed: status={res.status_code} response={data}")
      raise ValueError(
          data.get("errorMessage")
          or data.get("ResponseDescription")
          or f"STK failed ({res.status_code}): {data}"
      )
    return data


async def stk_query(checkout_request_id: str):
  token = await get_access_token()
  ts = get_timestamp()

  body = {
      "BusinessShortCode": SHORTCODE,
      "Password": build_password(ts),
      "Timestamp": ts,
      "CheckoutRequestID": checkout_request_id,
  }

  async with httpx.AsyncClient() as client:
    try:
      res = await client.post(
          f"{BASE}/mpesa/stkpushquery/v1/query",
          headers={
              "Authorization": f"Bearer {token}",
              "Content-Type": "application/json",
              "Accept": "application/json",
          },
          json=body,
      )
      return res.json()
    except Exception as e:
      print(f"[mpesa] STK query error: {e}")
      return None
