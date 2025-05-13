import os
import tempfile
from dotenv import load_dotenv
from deepgram import DeepgramClient, PrerecordedOptions
import speech_recognition as sr

load_dotenv()
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

class DeepgramSTT:
    def __init__(self):
        self.client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

    def transcribe_audio_file(self, audio_file_path: str, mimetype: str | None = None) -> str:
        """
        Transcribe a local audio file via Deepgram.
        - audio_file_path: path to .wav or .mp3 (or other supported)
        - mimetype: e.g. "audio/wav" or "audio/mpeg". If None, inferred from file extension.
        """
        # Infer mimetype from extension if not provided
        if mimetype is None:
            ext = os.path.splitext(audio_file_path)[1].lower()
            if ext == ".mp3":
                mimetype = "audio/mpeg"
            else:
                mimetype = "audio/wav"

        with open(audio_file_path, "rb") as audio:
            source = {"buffer": audio, "mimetype": mimetype}
            options = PrerecordedOptions(
                model="nova-3",
                smart_format=True,
                language="en-US",
            )
            response = self.client.listen.prerecorded.v("1").transcribe_file(source, options)
            # Return the top alternative transcript
            return response.results.channels[0].alternatives[0].transcript

    def transcribe_from_microphone(self, recognizer, source):
        audio = recognizer.listen(source, timeout=10)
        wav_data = audio.get_wav_data()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_file.write(wav_data)
            temp_path = temp_file.name

        result = self.transcribe_audio_file(temp_path)
        os.unlink(temp_path)
        return result
