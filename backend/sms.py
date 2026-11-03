import os
import africastalking
from dotenv import load_dotenv

load_dotenv()

username = os.getenv("AT_USERNAME", "sandbox")
api_key = os.getenv("AT_API_KEY", "")
sender_id = os.getenv("AT_SENDER_ID")

print(
    f"[sms] Initializing Africa's Talking with username={username},"
    f" apiKey={api_key[:6] if api_key else 'None'}..."
)

try:
  africastalking.initialize(username, api_key)
  sms = africastalking.SMS
except Exception as e:
  print(f"[sms] Initialization error: {e}")
  sms = None


def normalize_sms_phone(phone: str) -> str:
  p = str(phone or "").strip()
  if not p.startswith("+"):
    p = "+" + p
  return p


def send_sms(phone: str, message: str):
  if not sms:
    print("[sms] Africa's Talking SMS client not initialized.")
    return None
  try:
    recipient = normalize_sms_phone(phone)
    kwargs = {"message": message, "recipients": [recipient]}
    if sender_id:
      kwargs["sender_id"] = sender_id

    response = sms.send(**kwargs)
    print("SMS sent successfully:", response)
    return response
  except Exception as e:
    print(f"Failed to send SMS: {e}")
    import traceback
    traceback.print_exc()
    return None
