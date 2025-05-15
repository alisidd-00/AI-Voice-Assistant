# app/services/tts.py
import os
import tempfile
import threading
from pathlib import Path
from openai import OpenAI

# Your app’s public base URL (ngrok or production)
APP_BASE = os.getenv("TWILIO_WEBHOOK_BASE")
OPENAI_KEY = os.getenv("OPENAI_KEY")
_client = OpenAI(api_key=OPENAI_KEY)

def _schedule_delete(path: str, delay: int = 60):
    def _del():
        try:
            os.remove(path)
        except OSError:
            pass
    threading.Timer(delay, _del).start()

def generate_openai_tts(text: str, voice_type: str = "female") -> str:
    """
    Streams gpt-4o-mini-tts output into an MP3 file and returns a public URL.
    The file is scheduled for deletion after `delay` seconds.
    """
    # Map your assistant.voice_type → OpenAI voice names
    voice = "alloy" if voice_type.lower() == "male" else "coral"

    # Issue the streaming TTS request
    with _client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=text,
        instructions="Speak in a friendly, conversational tone.",
    ) as resp:
        # Prepare a temp file under static/tts so Twilio can <Play> it
        tmp = tempfile.NamedTemporaryFile(
            prefix="tts_", suffix=".mp3", delete=False, dir="static/tts"
        )
        path = tmp.name
        tmp.close()

        # use the SDK helper to write the entire stream
        resp.stream_to_file(path)

    # clean up after 60s
    _schedule_delete(path, delay=60)

    # build and return the public URL
    filename = Path(path).name
    return f"{APP_BASE}/static/tts/{filename}"
