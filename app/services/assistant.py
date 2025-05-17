# app/services/assistant.py

import json
from datetime import datetime
from app.services.memory import load_memory, save_memory_entry
from app.services.llm import query_openrouter
from app.services.utils import generate_prompt, extract_booking_data
from app.services.booking import handle_booking
from app.models import Assistant

def process_input(user_text: str, assistant: Assistant, conversation_id: int):
 
    history = load_memory(conversation_id)

    history_json = json.dumps(history, ensure_ascii=False)

    prompt      = generate_prompt(history_json, assistant)

    messages = [
        {"role": "system", "content": prompt},
        *history,
        {"role": "user",   "content": user_text}
    ]

    # 4) Send to LLM and strip out any [BOOKING:...] block
    reply, booking_data = extract_booking_data(query_openrouter(messages))
    save_memory_entry(conversation_id, "user", user_text)
    save_memory_entry(conversation_id, "assistant", reply)

    # 5) If booking_data present, parse and persist it
    if booking_data and "booking_confirmed" in booking_data:
        b = booking_data["booking_confirmed"]

        # parse date (or default to today)
        if b.get("date"):
            date_obj = datetime.strptime(b["date"], "%Y-%m-%d").date()
        else:
            date_obj = datetime.now().date()

        # parse time: try 12-hour then 24-hour
        raw = b["time"].strip()
        try:
            time_obj = datetime.strptime(raw, "%I:%M %p").time()
        except ValueError:
            time_obj = datetime.strptime(raw, "%H:%M").time()

        customer_name = b.get("name", "Unknown")
        details       = b.get("details", "")

        # your new DB-backed booking handler
        handle_booking(
            assistant_id=assistant.id,
            date=date_obj,
            time=time_obj,
            customer_name=customer_name,
            details=details
        )

    return reply, booking_data
