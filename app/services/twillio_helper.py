import os
from twilio.rest import Client

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
webhook_base = os.getenv("TWILIO_WEBHOOK_BASE")  # e.g., https://yourdomain.com/voice
client = Client(account_sid, auth_token)

def buy_twilio_number(country="US"):
    numbers = client.available_phone_numbers(country).local.list(limit=1)
    if not numbers:
        raise Exception("No Twilio numbers available")

    new_number = client.incoming_phone_numbers.create(
        phone_number=numbers[0].phone_number,
        voice_url=f"{webhook_base}/voice",
        voice_method="POST"
    )
    return new_number.phone_number
