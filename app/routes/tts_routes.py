import os
from flask import Blueprint, request, Response, stream_with_context
from openai import OpenAI

tts_bp = Blueprint("tts", __name__)

# initialize once with your API key from env
_client = OpenAI(api_key=os.environ["OPENAI_KEY"])

@tts_bp.route("/tts", methods=["GET"])
def tts_proxy():
    """
    Proxy endpoint that streams GPT-4o-mini-TTS audio directly to Twilio.
    Usage: GET /tts?text=Hello+world&voice=coral
    """
    text  = request.args.get("text", "")
    voice = request.args.get("voice", "coral")  # "coral" (female) or "alloy" (male)

    if not text:
        return ("No text provided", 400)

    def generate():
        try:
            # OpenAI streaming TTS
            response = _client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice=voice,
                input=text,
                instructions="Speak in a friendly, conversational tone.",
            )
            
            # Stream the binary content directly
            for chunk in response.iter_bytes():
                yield chunk
                
        except Exception as e:
            # on error, yield silence or break
            print(f"TTS streaming error: {e}")
            # optionally yield a brief silent mp3 frame or simply stop
            return

    return Response(
        stream_with_context(generate()),
        mimetype="audio/mpeg",
        headers={
            # tell Twilio to buffer minimally
            "Cache-Control": "no-cache"
        }
    )