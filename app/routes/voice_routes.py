from flask import Blueprint, request, Response
from app.models import Assistant, Conversation
from twilio.twiml.voice_response import VoiceResponse, Connect
from app.extensions import db
from app.services.memory import save_memory_entry
from app import sock
from app.services.realtime_processing import CallHandler
import asyncio

voice_bp = Blueprint("voice", __name__)
active_calls = {}

@voice_bp.route("/voice", methods=["POST"])
def voice_entrypoint():
    """Initial voice call handler that connects to the WebSocket for real-time processing."""
    to_number = request.form.get("To")
    assistant = Assistant.query.filter_by(twilio_number=to_number).first()
    from_number = request.form["From"]

    # Find or create conversation
    convo = Conversation.query.filter_by(
        assistant_id=assistant.id,
        caller_number=from_number
    ).first()
    
    if not convo:
        convo = Conversation(assistant_id=assistant.id, caller_number=from_number)
        db.session.add(convo)
        db.session.commit()

    
    # Build TwiML to connect into our WebSocket
    resp = VoiceResponse()
    
    # Set the voice to match what will be used in the stream
    voice = "man" if assistant.voice_type.lower() == "male" else "woman"
    
    # Don't actually say the greeting - we'll let the OpenAI stream handle it
    # We're just connecting to the websocket immediately
    host = request.host_url.replace("http://", "").replace("https://", "").rstrip("/")
    connect = Connect()
    connect.stream(url=f"wss://{host}/ws/call/{convo.id}")
    resp.append(connect)

    return Response(str(resp), mimetype="text/xml")

@sock.route("/ws/call/<int:conversation_id>")
def call_websocket(ws, conversation_id):
    """
    WebSocket handler for real-time call processing.
    This remains a synchronous function so Flask-Sock will invoke it directly.
    We then drive your async CallHandler with asyncio.run().
    """
    # Look up models
    convo = Conversation.query.get_or_404(conversation_id)
    assistant = Assistant.query.get_or_404(convo.assistant_id)

    handler = CallHandler(
        websocket=ws,
        assistant=assistant,
        conversation_id=conversation_id
    )
    active_calls[conversation_id] = handler

    try:
        # Run your async loop to completion
        asyncio.run(handler.process())
    except Exception as e:
        print(f"Error in WebSocket handler: {e}")
    finally:
        active_calls.pop(conversation_id, None)
