# app/routes/assistant_routes.py

from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import json
from datetime import datetime, timedelta

from app.models import db, User, Assistant, Booking
from app.services.twillio_helper import buy_twilio_number
from app.services.rag import extract_and_index
from app.services.booking import generate_time_slots, load_booked_slots
from flask import session

assistant_bp = Blueprint("assistant", __name__)

@assistant_bp.route("/register", methods=["POST"])
def register_business():
    """
    Accepts multipart/form-data with form fields:
      - user_id (int)
      - business_name
      - receptionist_name
      - start_time (HH:MM)
      - end_time   (HH:MM)
      - booking_duration_minutes (int)
      - phone_number
      - available_days (JSON object)
      - voice_type ("male"|"female")
    Optionally:
      - files (one or more PDFs or text files) to index into RAG immediately.
    """
    print("🔍 Request:", request)
    # 1) Parse and validate core form fields
    form = request.form
    print("🔍 Form:", form)
    try:
        user_id = int(form["user_id"])
    except (KeyError, ValueError):
        return jsonify(error="Must include a valid user_id"), 400

    required = [
        "business_name",
        "receptionist_name",
        "start_time",
        "end_time",
        "booking_duration_minutes",
        "phone_number",
        "available_days",
        "voice_type"
    ]
    if not all(field in form for field in required):
        return jsonify(error="Missing one or more required fields"), 400

    user = User.query.get(user_id)
    print("🔍 User:", user)
    if not user:
        return jsonify(error="No such user"), 404
    
    country = form.get("country", "US").upper()
    # 2) Acquire or purchase Twilio number
    twilio_number = form.get("twilio_number")
    if not twilio_number:
        try:
            twilio_number = buy_twilio_number(country)
        except Exception as e:
            return jsonify(error="Twilio error", details=str(e)), 500

    # 3) Create the Assistant record
    assistant = Assistant(
        name=form["receptionist_name"],
        business_name=form["business_name"],
        description=form.get("business_description", ""),
        start_time=form["start_time"],
        end_time=form["end_time"],
        booking_duration_minutes=int(form["booking_duration_minutes"]),
        available_days=json.dumps(json.loads(form["available_days"])),
        twilio_number=twilio_number,
        voice_type=form["voice_type"],
        user_id=user.id
    )
    db.session.add(assistant)
    db.session.commit()

    # 4) Optional: immediately index any uploaded files via RAG
    indexed = 0
    if "files" in request.files:
        docs = []
        for f in request.files.getlist("files"):
            filename = secure_filename(f.filename or "")
            ext = filename.rsplit(".", 1)[-1].lower()
            data = f.read()
            if ext == "pdf":
                docs.append(data)
            elif ext in ("txt", "md", "text"):
                docs.append(data.decode("utf-8", errors="ignore"))
        if docs:
            result = extract_and_index(assistant.id, user.id, docs)
            indexed = result.get("indexed", 0)

    # 5) Return response
    resp = {
        "message":       f"Assistant created. Forward calls to {twilio_number}.",
        "assistant_id":  assistant.id,
        "twilio_number": twilio_number,
        "indexed_chunks": indexed
    }
    return jsonify(resp), 201


@assistant_bp.route("/slots/<int:assistant_id>", methods=["GET"])
def get_available_slots(assistant_id):
    """
    Query params:
      - date (YYYY-MM-DD) optional, defaults to today
    """
    assistant = Assistant.query.get_or_404(assistant_id)
    date_str = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify(error="Invalid date format, use YYYY-MM-DD"), 400

    day = date.strftime("%A").lower()
    try:
        available_days = json.loads(assistant.available_days)
    except:
        available_days = {
            "monday": True, "tuesday": True, "wednesday": True,
            "thursday": True, "friday": True,
            "saturday": False, "sunday": False
        }

    if not available_days.get(day, False):
        return jsonify(date=date_str, day=day, slots=[], message=f"No slots on {day.capitalize()}"), 200

    slots = generate_time_slots(
        assistant.start_time,
        assistant.end_time,
        assistant.booking_duration_minutes,
        available_days,
        for_date=date.date()
    )
    booked = load_booked_slots(assistant.id, date.date())

    free = [s for s in slots if f"{date_str}_{s}" not in booked or booked[f"{date_str}_{s}"] is None]
    return jsonify(
        date=date_str,
        day=day,
        slots=free,
        business_hours=f"{assistant.start_time} - {assistant.end_time}",
        slot_duration=assistant.booking_duration_minutes
    ), 200


@assistant_bp.route("/bookings/<int:assistant_id>", methods=["GET"])
def get_assistant_bookings(assistant_id):
    """
    Query params:
      - start_date (YYYY-MM-DD), default=today
      - end_date   (YYYY-MM-DD), default=start+7d
    """
    assistant = Assistant.query.get_or_404(assistant_id)

    # parse date range
    sd = request.args.get("start_date")
    ed = request.args.get("end_date")
    try:
        start = datetime.strptime(sd, "%Y-%m-%d").date() if sd else datetime.now().date()
        end   = datetime.strptime(ed, "%Y-%m-%d").date() if ed else start + timedelta(days=7)
    except ValueError:
        return jsonify(error="Invalid date format, use YYYY-MM-DD"), 400

    # fetch bookings
    rows = Booking.query.filter_by(assistant_id=assistant_id) \
        .filter(Booking.date >= start, Booking.date <= end) \
        .order_by(Booking.date, Booking.time) \
        .all()

    bookings = [{
        "id":            b.id,
        "date":          b.date.strftime("%Y-%m-%d"),
        "time":          b.time.strftime("%H:%M"),
        "customer_name": b.customer_name,
        "details":       b.details,
        "created_at":    b.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for b in rows]

    # build slots per day
    all_slots = {}
    current = start
    try:
        available_days = json.loads(assistant.available_days)
    except:
        available_days = {}
    while current <= end:
        day = current.strftime("%A").lower()
        if available_days.get(day, False):
            day_slots = generate_time_slots(
                assistant.start_time,
                assistant.end_time,
                assistant.booking_duration_minutes,
                available_days,
                for_date=current
            )
            booked_map = load_booked_slots(assistant.id, current)
            formatted = []
            for slot in day_slots:
                t24 = datetime.strptime(slot, "%I:%M %p").strftime("%H:%M")
                is_booked = f"{current.strftime('%Y-%m-%d')}_{slot}" in booked_map
                formatted.append({"time": t24, "is_booked": is_booked})
            all_slots[current.strftime("%Y-%m-%d")] = formatted
        current += timedelta(days=1)

    return jsonify(
        bookings=bookings,
        slots=all_slots,
        business_hours=f"{assistant.start_time} - {assistant.end_time}",
        slot_duration=assistant.booking_duration_minutes
    ), 200


@assistant_bp.route("/assistants", methods=["GET"])
def list_assistants():
    """
    GET /api/assistants?user_id=123
    or if you have session-based auth, omit the query-param and rely on session["user_id"].
    """
    # Try session first (if you have a login flow), otherwise fall back to ?user_id=
    user_id = session.get("user_id") or request.args.get("user_id", type=int)
    if not user_id:
        return jsonify(error="Missing user_id"), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify(error="No such user"), 404

    assistants = Assistant.query.filter_by(user_id=user_id).all()

    payload = []
    for a in assistants:
        payload.append({
            "id": a.id,
            "name": a.name,
            "business_name": a.business_name,
            "description": a.description,
            "start_time": a.start_time,
            "end_time": a.end_time,
            "booking_duration_minutes": a.booking_duration_minutes,
            "available_days": json.loads(a.available_days),
            "twilio_number": a.twilio_number,
            "voice_type": a.voice_type
        })

    return jsonify(assistants=payload), 200

@assistant_bp.route("/assistant/<int:assistant_id>", methods=["PATCH"])
def update_assistant(assistant_id):
    """
    Update fields on an existing Assistant.
    Accepts JSON body with any of:
      - business_name (str)
      - receptionist_name (str)      → maps to Assistant.name
      - description (str)
      - start_time (HH:MM)
      - end_time   (HH:MM)
      - booking_duration_minutes (int)
      - available_days (JSON object of day→bool)
      - voice_type ("male" or "female")
    (Note: twilio_number and user’s phone_number cannot be changed here.)
    """
    data = request.get_json(force=True, silent=True) or {}
    assistant = Assistant.query.get_or_404(assistant_id)

    # Only allow these fields to be updated
    updatable = {
        "business_name":           lambda v: setattr(assistant, "business_name", v),
        "receptionist_name":       lambda v: setattr(assistant, "name", v),
        "description":             lambda v: setattr(assistant, "description", v),
        "start_time":              lambda v: setattr(assistant, "start_time", v),
        "end_time":                lambda v: setattr(assistant, "end_time", v),
        "booking_duration_minutes":lambda v: setattr(assistant, "booking_duration_minutes", int(v)),
        "voice_type":              lambda v: setattr(assistant, "voice_type", v),
        "available_days":          lambda v: setattr(assistant, "available_days", json.dumps(v)),
    }

    changed = []
    for field, setter in updatable.items():
        if field in data:
            try:
                setter(data[field])
                changed.append(field)
            except (ValueError, TypeError):
                return jsonify(error=f"Invalid value for `{field}`"), 400

    if not changed:
        return jsonify(message="No updatable fields provided"), 400

    db.session.commit()

    # Return the updated assistant record
    assistant_data = {
        "id":                         assistant.id,
        "name":                       assistant.name,
        "business_name":              assistant.business_name,
        "description":                assistant.description,
        "start_time":                 assistant.start_time,
        "end_time":                   assistant.end_time,
        "booking_duration_minutes":   assistant.booking_duration_minutes,
        "voice_type":                 assistant.voice_type,
        "available_days":             json.loads(assistant.available_days),
    }

    return jsonify(
        message="Assistant updated successfully",
        updated_fields=changed,
        assistant=assistant_data
    ), 200
