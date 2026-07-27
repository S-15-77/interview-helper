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
    segments, _ = model.transcribe(audio, language="en")
    return " ".join(segment.text.strip() for segment in segments).strip()
