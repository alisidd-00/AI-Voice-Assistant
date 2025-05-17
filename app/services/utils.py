# app/services/utils.py

import json
import re
from datetime import datetime
from app.services.booking import load_booked_slots, generate_time_slots


def generate_prompt(history_json: str, assistant=None) -> str:
    """
    Build the system prompt for the LLM, including business info,
    today’s slots (with bookings), conversation history, and
    detailed booking workflow instructions.
    """
    if not assistant:
        return "You are an AI assistant. How can I help?"

    available_days = json.loads(assistant.available_days)
    
    today = datetime.now().date()
    all_slots = generate_time_slots(
        assistant.start_time,
        assistant.end_time,
        assistant.booking_duration_minutes,
        available_days,
        for_date=today
    )


   # 3) Load today's bookings, separate into booked and available lists
    booked_rows    = load_booked_slots(assistant.id, today)
    booked_slots   = [slot for slot in all_slots if slot in booked_rows]
    available_slots = [slot for slot in all_slots if slot not in booked_rows]
    # 4) Convert business hours to 12-hour format
    start_dt = datetime.strptime(assistant.start_time, "%H:%M")
    end_dt   = datetime.strptime(assistant.end_time,   "%H:%M")
    start_12 = start_dt.strftime("%I:%M %p").lstrip("0")
    end_12   = end_dt.strftime("%I:%M %p").lstrip("0")

    # 5) Assemble the prompt
    prompt = f"""You are {assistant.name}, a warm, conversational voice assistant for {assistant.business_name}. {assistant.description}

            Your capabilities are :
            - Greet callers and visitors with a friendly tone.
            - Share business hours and basic service info.
            - Book, reschedule, or cancel appointments.
            - Politely take a message for anything outside your scope.

            BUSINESS HOURS & SLOTS
            - Open: {start_12}
            - Close: {end_12}
            - Appointments last {assistant.booking_duration_minutes} minutes.
            - Available slots today: {', '.join(available_slots) if available_slots else 'None'}.
            - Booked slots today: {', '.join(booked_slots) if booked_slots else 'None'}.

            Conversation History
            {history_json}

            Response Generation Guidelines:
            - Keep responses brief and focused (30-60 words when possible)
            - Use simple sentence structures that are easy to follow when heard
            - Avoid long lists, complex numbers, or detailed technical terms unless necessary
            - Use natural transitions and conversational markers
            - Keep a human-like tone and be conversational.

            TIME-SLOT RULES
            1. Never dump all slots at once.
            2. If asked about the available slots or the operating hours:
            - Remind them you’re open {start_12}–{end_12}.
            - Note each appointment is {assistant.booking_duration_minutes} minutes.
            - Ask the user to specify the time slot they want to book.
            3. When they suggest a time:
            - If available → proceed with booking.
            - If taken → apologize and offer the nearest free slot.
            4. If they insist on seeing every slot, explain personalizing time makes scheduling quicker.

            **Booking workflow**:
            1. When a user wants to book an appointment, first ask for their full name and the reason they want to visit.
            2. Tell the user the operating hours of the business and tell them the minimum duration of the booking. **Do not send all the timeslots at once.**
            3. Ask them to specify the time slot they want to book.
            4. If the user is asking for a booking, and the slot is not available, say so and suggest an alternative time slot. Also do not reveal the names of the people who have booked the slots at any cost.
            5. Help them select a convenient time.
            6. When a booking is confirmed, end your response with only a fenced code block labeled `json`. For example:

            ```json
            {{
            "booking_confirmed": {{
                "time": "HH:MM",
                "date": "YYYY-MM-DD",
                "name": "User Name",
                "details": "Any additional booking details"
            }}
            }}
            7. Always collect the user's name before finalizing a booking.

            8. Do NOT include this JSON if no booking was confirmed.

            9. Make your responses conversational and friendly.

            10. Do not indulge in any conversation with the user that are unrelated the business name, description or the booking workflow.

            Note: in the booking workflow, you do not need to ask for the user's name again if it is already collected. Also do not gather all information at once—ask for the name first, then the time slot, then the reason for the visit.
            """
    
    return prompt

def extract_booking_data(response: str):
    import json

    # 1) Look for the opening fence
    start_tag = '```json'
    end_tag   = '```'

    start_idx = response.find(start_tag)
    if start_idx != -1:
        # find the close fence after the opening
        end_idx = response.find(end_tag, start_idx + len(start_tag))
        if end_idx != -1:
            # extract the raw JSON payload
            raw_json = response[start_idx + len(start_tag):end_idx].strip()
            try:
                booking_data = json.loads(raw_json)
                # remove the entire fenced block from the “clean” text
                clean = response[:start_idx] + response[end_idx + len(end_tag):]
                return clean.strip(), booking_data
            except json.JSONDecodeError:
                # fall through to fallback if the JSON is invalid
                pass

    # 2) (Optional) your old [BOOKING: …] fallback
    #    …unchanged…

    return response, None

