from app.extensions import db 
from datetime import datetime


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    email = db.Column(db.String(120), unique=True, nullable=True)
    google_id = db.Column(db.String(120), unique=True, nullable=True)
    google_token = db.Column(db.Text, nullable=True)
    google_refresh_token = db.Column(db.Text, nullable=True)

    assistants = db.relationship("Assistant", backref="owner", lazy=True)

class Assistant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    business_name = db.Column(db.String(120))
    description = db.Column(db.Text)
    start_time = db.Column(db.String(5))
    end_time = db.Column(db.String(5))
    booking_duration_minutes = db.Column(db.Integer)
    available_days = db.Column(db.Text)  # JSON string of available days
    twilio_number = db.Column(db.String(20))
    voice_type = db.Column(db.String(10), default="female")
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class Booking(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    assistant_id   = db.Column(db.Integer, db.ForeignKey("assistant.id"), nullable=False)
    date           = db.Column(db.Date, nullable=False)
    time           = db.Column(db.Time, nullable=False)
    customer_name  = db.Column(db.String(80), nullable=False)
    details        = db.Column(db.Text)
    created_at     = db.Column(db.DateTime, server_default=db.func.now())



class Conversation(db.Model):
    __tablename__ = "conversation"
    id             = db.Column(db.Integer, primary_key=True)
    assistant_id   = db.Column(db.Integer, db.ForeignKey("assistant.id"), nullable=False)
    caller_number  = db.Column(db.String(20), nullable=False)
    created_at     = db.Column(db.DateTime, server_default=db.func.now())

    messages       = db.relationship("Message", backref="conversation", lazy=True)


class Message(db.Model):
    __tablename__ = "message"
    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id"), nullable=False)
    role            = db.Column(db.String(20), nullable=False)   # "user" or "assistant"
    content         = db.Column(db.Text,   nullable=False)
    created_at      = db.Column(db.DateTime, server_default=db.func.now())
