import os
import json
from app.models import Message
from app.extensions import db

def load_memory(conversation_id: int) -> list[dict]:
    """Load conversation history from database."""
    rows = (
        Message.query
               .filter_by(conversation_id=conversation_id)
               .order_by(Message.created_at)
               .all()
    )
    return [{"role": m.role, "content": m.content} for m in rows]

def save_memory_entry(conversation_id: int, role: str, content: str):
    """Save a new message to the conversation history in database."""
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content
    )
    db.session.add(msg)
    db.session.commit()
    return msg
