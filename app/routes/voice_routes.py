from flask import Blueprint, request, Response
from app.models import Assistant, Conversation, Message
from twilio.twiml.voice_response import VoiceResponse
from app.services.tts import generate_openai_tts  
from twilio.rest import Client
from app.extensions import db
from app.services.memory import save_memory_entry

voice_bp = Blueprint("voice", __name__)

@voice_bp.route("/voice", methods=["POST"])
def voice_entrypoint():
    to_number = request.form.get("To")
    assistant = Assistant.query.filter_by(twilio_number=to_number).first()
    print("Incoming call for assistant:", assistant)
    from_number = request.form["From"]

    convo = Conversation.query.filter_by(
        assistant_id=assistant.id,
        caller_number=from_number
    ).first()
    if not convo:
        convo = Conversation(assistant_id=assistant.id, caller_number=from_number)
        db.session.add(convo)
        db.session.commit()

    greeting = f"Hi, this is {assistant.name} from {assistant.business_name}. How can I help you today?"

    save_memory_entry(convo.id, "assistant", greeting)
    audio_url = generate_openai_tts(greeting, assistant.voice_type)
    print("🕪 Playing back via:", audio_url)

    resp = VoiceResponse()
    resp.play(audio_url)

    # old record-based flow (commented out):
    # resp.record(
    #     action=f"/voice/process-recording?assistant_id={assistant.id}",
    #     play_beep=True,
    #     max_length=30
    # )

    # new gather-based flow:
    resp.gather(
        input="speech",
        speechTimeout="auto",  # Twilio will detect end-of-speech
        action=f"/voice/process-recording?assistant_id={assistant.id}",
        method="POST"
    )
    return Response(str(resp), mimetype="text/xml")


@voice_bp.route("/process-recording", methods=["POST"])
def process_recording():
    from flask import Response, request
    from twilio.twiml.voice_response import VoiceResponse
    from twilio.rest import Client
    from app.services.assistant import process_input
    from app.services.tts import generate_openai_tts  
    # from app.services.stt import DeepgramSTT   # only needed for fallback

    # 1) Lookup assistant
    assistant_id = request.args.get("assistant_id")
    assistant    = Assistant.query.get_or_404(assistant_id)
    from_number  = request.form["From"]

    # fetch the convo we created in /voice
    convo = Conversation.query.filter_by(
        assistant_id=assistant.id,
        caller_number=from_number
    ).first()

    # 2) Attempt to read Twilio’s built-in ASR result:
    user_text = request.form.get("SpeechResult")
    if user_text:
        print("👉 Gather ASR text:", user_text)
 
    reply, booking_data = process_input(user_text, assistant, convo.id)
    print("Assistant reply:", reply, "booking_data:", booking_data)

    # 5) Generate your TTS reply
    audio_url = generate_openai_tts  (reply, assistant.voice_type)
    print("🕪 Playing back via:", audio_url)

    # 6) Build TwiML: play + either hang up or gather again
    vr = VoiceResponse()
    vr.play(audio_url)

    if booking_data:
        vr.hangup()
    else:
        # old record fallback (commented):
        # vr.record(
        #     action=f"/voice/process-recording?assistant_id={assistant.id}",
        #     play_beep=True,
        #     max_length=30
        # )

        # continue with gather
        vr.gather(
            input="speech",
            speechTimeout="auto",
            action=f"/voice/process-recording?assistant_id={assistant.id}",
            method="POST"
        )

    return Response(str(vr), mimetype="text/xml")


# app/routes/voice_routes.py

# from flask import Blueprint, request, Response
# from app.models import Assistant, Conversation
# from twilio.twiml.voice_response import VoiceResponse
# from app.services.memory import save_memory_entry
# from twilio.rest import Client
# from app.extensions import db
# from app.services.assistant import process_input

# # we no longer need generate_openai_tts here
# from urllib.parse import quote_plus

# voice_bp = Blueprint("voice", __name__)

# @voice_bp.route("/voice", methods=["POST"])
# def voice_entrypoint():
#     to_number   = request.form["To"]
#     from_number = request.form["From"]
#     assistant   = Assistant.query.filter_by(twilio_number=to_number).first()

#     # find or create this call's Conversation
#     convo = (Conversation
#              .query
#              .filter_by(assistant_id=assistant.id, caller_number=from_number)
#              .first())
#     if not convo:
#         convo = Conversation(assistant_id=assistant.id, caller_number=from_number)
#         db.session.add(convo)
#         db.session.commit()

#     greeting = f"Hi, this is {assistant.name} from {assistant.business_name}. How can I help you today?"
#     # save into DB
#     save_memory_entry(convo.id, "assistant", greeting)

#     # build your streaming‐TTS URL
#     base     = request.url_root.rstrip("/")
#     tts_text = quote_plus(greeting)
#     voice_nm = "alloy" if assistant.voice_type.lower()=="male" else "coral"
#     audio_url = f"{base}/tts?text={tts_text}&voice={voice_nm}"

#     resp = VoiceResponse()
#     resp.play(audio_url)
#     resp.gather(
#         input="speech",
#         speechTimeout="auto",
#         action=f"/voice/process-recording?assistant_id={assistant.id}",
#         method="POST"
#     )
#     return Response(str(resp), mimetype="text/xml")


# @voice_bp.route("/process-recording", methods=["POST"])
# def process_recording():
#     to_number   = request.form["To"]
#     from_number = request.form["From"]
#     assistant   = Assistant.query.get_or_404(request.args["assistant_id"])

#     # re-load conversation
#     convo = (Conversation
#              .query
#              .filter_by(assistant_id=assistant.id, caller_number=from_number)
#              .first())

#     # 1) get Twilio's ASR result
#     user_text = request.form.get("SpeechResult", "").strip()
#     if not user_text:
#         # if no SpeechResult, you could fallback to Record+Deepgram here
#         user_text = "..."  # or handle error

#     print("User said:", user_text)
#     save_memory_entry(convo.id, "user", user_text)

#     # 2) run LLM + booking logic
#     reply, booking_data = process_input(user_text, assistant, convo.id)
#     print("Assistant reply:", reply, "booking_data:", booking_data)
#     save_memory_entry(convo.id, "assistant", reply)

#     # 3) stream back via /tts
#     base     = request.url_root.rstrip("/")
#     tts_text = quote_plus(reply)
#     voice_nm = "alloy" if assistant.voice_type.lower()=="male" else "coral"
#     audio_url = f"{base}/tts?text={tts_text}&voice={voice_nm}"

#     vr = VoiceResponse()
#     vr.play(audio_url)

#     if booking_data:
#         vr.hangup()
#     else:
#         vr.gather(
#             input="speech",
#             speechTimeout="auto",
#             action=f"/voice/process-recording?assistant_id={assistant.id}",
#             method="POST"
#         )

#     return Response(str(vr), mimetype="text/xml")
