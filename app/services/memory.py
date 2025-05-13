import os
import json
from app.models import Message
from app.extensions import db

# MEM_PATH = lambda caller_id: f"memory_{caller_id}.json"
# USER_INFO_PATH = "user_info.json"

def load_memory(conversation_id: int) -> list[dict]:
    rows = (
        Message.query
               .filter_by(conversation_id=conversation_id)
               .order_by(Message.created_at)
               .all()
    )
    return [{"role": m.role, "content": m.content} for m in rows]

def save_memory_entry(conversation_id: int, role: str, content: str):
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content
    )
    db.session.add(msg)
    db.session.commit()

# def load_memory(caller_id):
#     if os.path.exists(MEM_PATH(caller_id)):
#         with open(MEM_PATH(caller_id), "r", encoding="utf-8") as f:
#             return json.load(f)
#     return []

# def save_memory(history, caller_id):
#     with open(MEM_PATH(caller_id), "w", encoding="utf-8") as f:
#         json.dump(history, f, ensure_ascii=False, indent=2)

# def load_user_info():
#     if os.path.exists(USER_INFO_PATH):
#         with open(USER_INFO_PATH, "r", encoding="utf-8") as f:
#             return json.load(f)
#     return {}

# def save_user_info(user_info):
#     with open(USER_INFO_PATH, "w", encoding="utf-8") as f:
#         json.dump(user_info, f, ensure_ascii=False, indent=2)

# def get_user_name(user_id):
#     user_info = load_user_info()
#     return user_info.get(user_id, {}).get("name")

# def update_user_info(user_id, name, contact=None, preferences=None):
#     user_info = load_user_info()

#     if user_id not in user_info:
#         user_info[user_id] = {}

#     if name:
#         user_info[user_id]["name"] = name
#     if contact:
#         user_info[user_id]["contact"] = contact
#     if preferences:
#         user_info[user_id]["preferences"] = preferences

#     save_user_info(user_info)
#     return user_info[user_id]
