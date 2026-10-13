"""Voice layer: faster-whisper speech-to-text and Piper text-to-speech, both offline on CPU."""
import io
import threading
import wave

from faster_whisper import WhisperModel
from piper import PiperVoice


class STT:
    def __init__(self, model, threads=4):
        self.model = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads)
        self.lock = threading.Lock()

    def transcribe(self, audio: bytes):
        with self.lock:
            segs, info = self.model.transcribe(io.BytesIO(audio), language="en", vad_filter=True, beam_size=1)
            text = " ".join(s.text.strip() for s in segs).strip()
        return {"text": text, "audio_seconds": round(info.duration, 2)}


class TTS:
    """Many Piper voices; each is loaded the first time it is used."""

    def __init__(self, voice_dir, default):
        self.dir, self.default = voice_dir, default
        self.voices, self.lock = {}, threading.Lock()
        self.get(default)

    def names(self):
        return sorted(f.name.removesuffix(".onnx") for f in self.dir.glob("*.onnx"))

    def get(self, name):
        with self.lock:
            if name not in self.voices:
                if name not in self.names():
                    raise ValueError(f"unknown voice {name!r}")
                self.voices[name] = PiperVoice.load(str(self.dir / f"{name}.onnx"))
            return self.voices[name]

    def synthesize(self, text, voice=None):
        v = self.get(voice or self.default)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            v.synthesize_wav(text, w)
        return buf.getvalue()
