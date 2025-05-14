from flask import request
from app.services.booking import generate_time_slots, load_booked_slots
# from app.services.memory import update_user_info
import os
import json
from flask import Blueprint, request, jsonify
from app.models import db, User, Assistant, Booking
from app.services.twillio_helper import buy_twilio_number
from datetime import datetime, timedelta

assistant_bp = Blueprint("assistant", __name__)  # ✅ Define this first

@assistant_bp.route("/register", methods=["POST"])
def register_business():
    data = request.json
    if "user_id" not in data:
        return {"error": "Must include your user_id"}, 400
    
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

    if not all(field in data for field in required):
        return {"error": "Missing required fields"}, 400
    
    user = User.query.get(data["user_id"])
    if not user:
        return {"error": "No such user"}, 404
    
    # Use existing Twilio number if provided, otherwise buy a new one
    twilio_number = data.get("twilio_number")
    if not twilio_number:
        try:
            print('1')
            # twilio_number = buy_twilio_number()
        except Exception as e:
            return {"error": "Twilio error", "details": str(e)}, 500

    # Create assistant
    assistant = Assistant(
        name=data["receptionist_name"],
        business_name=data["business_name"],
        description=data.get("business_description", ""),
        start_time=data["start_time"],
        end_time=data["end_time"],
        booking_duration_minutes=data["booking_duration_minutes"],
        available_days=json.dumps(data["available_days"]),
        twilio_number=twilio_number,
        voice_type=data["voice_type"], 
        user_id=user.id
    )
    db.session.add(assistant)
    db.session.commit()

    return {
        "message": f"Assistant created. Forward your calls to {twilio_number}.",
        "twilio_number": twilio_number
    }, 201

@assistant_bp.route("/slots/<int:assistant_id>", methods=["GET"])
def get_available_slots(assistant_id):
    from datetime import datetime
    import json
    
    assistant = Assistant.query.get_or_404(assistant_id)
    
    # Get query parameters
    date_str = request.args.get('date')
    
    # If no date provided, use today
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400
        
    # Get day of week
    day_name = date.strftime("%A").lower()
    
    # Parse available days
    available_days = {}
    if assistant.available_days:
        try:
            available_days = json.loads(assistant.available_days)
        except:
            available_days = {
                "monday": True, "tuesday": True, "wednesday": True, 
                "thursday": True, "friday": True, 
                "saturday": False, "sunday": False
            }
    
    # Check if this day is available
    if not available_days.get(day_name, False):
        return {"slots": [], "message": f"No slots available on {day_name.capitalize()}"}, 200
    
    # Generate time slots for this day
    from app.services.booking import generate_time_slots, load_booked_slots
    slots = generate_time_slots(
        assistant.start_time, 
        assistant.end_time, 
        assistant.booking_duration_minutes,
        available_days,
        for_date=date.date()
    )
    
    # Load booked slots
    booked_slots = load_booked_slots(assistant.id, date.date())

    
    # Filter out booked slots
    available_slots = []
    for slot in slots:
        # Check if this slot is booked for this date
        slot_key = f"{date_str}_{slot}"
        if slot_key not in booked_slots or booked_slots[slot_key] is None:
            available_slots.append(slot)
    
    return {
        "date": date_str,
        "day": day_name,
        "slots": available_slots,
        "business_hours": f"{assistant.start_time} - {assistant.end_time}",
        "slot_duration": assistant.booking_duration_minutes
    }, 200

@assistant_bp.route("/bookings/<int:assistant_id>", methods=["GET"])
def get_assistant_bookings(assistant_id):
    """
    Get all bookings for an assistant within a date range
    Query parameters:
    - start_date: Start date in YYYY-MM-DD format (default: today)
    - end_date: End date in YYYY-MM-DD format (default: 7 days from start)
    """
    assistant = Assistant.query.get_or_404(assistant_id)
    
    # Get query parameters
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # If no start date provided, use today
    if not start_date_str:
        start_date = datetime.now().date()
    else:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid start_date format. Use YYYY-MM-DD"}, 400
    
    # If no end date provided, use 7 days from start date
    if not end_date_str:
        end_date = start_date + timedelta(days=7)
    else:
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid end_date format. Use YYYY-MM-DD"}, 400
    
    # Get all bookings for the assistant within the date range
    bookings = Booking.query.filter_by(assistant_id=assistant_id).filter(
        Booking.date >= start_date,
        Booking.date <= end_date
    ).all()
    
    # Format bookings for response
    formatted_bookings = []
    for booking in bookings:
        formatted_bookings.append({
            "id": booking.id,
            "date": booking.date.strftime("%Y-%m-%d"),
            "time": booking.time.strftime("%H:%M"),
            "customer_name": booking.customer_name,
            "details": booking.details,
            "created_at": booking.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    # Generate all available slots for each day in the range
    all_slots = {}
    current_date = start_date
    while current_date <= end_date:
        day_name = current_date.strftime("%A").lower()
        
        # Parse available days
        available_days = {}
        if assistant.available_days:
            try:
                available_days = json.loads(assistant.available_days)
            except:
                available_days = {
                    "monday": True, "tuesday": True, "wednesday": True, 
                    "thursday": True, "friday": True, 
                    "saturday": False, "sunday": False
                }
        
        # Skip if this day is not available
        if not available_days.get(day_name, False):
            current_date += timedelta(days=1)
            continue
        
        # Generate time slots for this day
        day_slots = generate_time_slots(
            assistant.start_time, 
            assistant.end_time, 
            assistant.booking_duration_minutes,
            available_days,
            for_date=current_date
        )
        
        # Load booked slots for this day
        booked_slots = load_booked_slots(assistant.id, current_date)
        
        # Format slots with availability info
        formatted_slots = []
        for slot in day_slots:
            # Convert 12-hour format to 24-hour format for consistency
            time_obj = datetime.strptime(slot, "%I:%M %p")
            time_24h = time_obj.strftime("%H:%M")
            
            # Check if slot is booked
            is_booked = time_obj.time() in [booking.time for booking in booked_slots.values()] if booked_slots else False
            
            formatted_slots.append({
                "time": time_24h,
                "is_booked": is_booked
            })
            
        all_slots[current_date.strftime("%Y-%m-%d")] = formatted_slots
        current_date += timedelta(days=1)
    
    return jsonify({
        "bookings": formatted_bookings,
        "slots": all_slots,
        "business_hours": f"{assistant.start_time} - {assistant.end_time}",
        "slot_duration": assistant.booking_duration_minutes
    })
