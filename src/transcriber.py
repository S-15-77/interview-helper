import numpy as np
from faster_whisper import WhisperModel

_MODEL: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = WhisperModel("base.en", device="auto", compute_type="int8")
    return _MODEL


def transcribe(audio: np.ndarray, sample_rate: int = 16000) -> str:
    model = _get_model()
    # vad_filter runs faster-whisper's built-in Silero VAD over the audio before
    # decoding, dropping silence/noise stretches. Without it, Whisper still "confidently"
    # invents plausible-sounding text for non-speech audio (comfort noise from a muted
    # call, background hiss) instead of returning nothing.
    segments, _ = model.transcribe(audio, language="en", vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()


def preload() -> None:
    _get_model()
