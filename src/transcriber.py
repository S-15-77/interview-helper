import math
from dataclasses import dataclass

import numpy as np
from faster_whisper import WhisperModel

_MODEL: WhisperModel | None = None
MIN_TRANSCRIPTION_CONFIDENCE = 0.25
MAX_NO_SPEECH_PROBABILITY = 0.65


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    confidence: float
    no_speech_probability: float

    @property
    def is_reliable(self) -> bool:
        return (
            bool(self.text.strip())
            and self.confidence >= MIN_TRANSCRIPTION_CONFIDENCE
            and self.no_speech_probability <= MAX_NO_SPEECH_PROBABILITY
        )


def _get_model() -> WhisperModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = WhisperModel("base.en", device="auto", compute_type="int8")
    return _MODEL


def transcribe_with_metadata(
    audio: np.ndarray,
    sample_rate: int = 16000,
) -> TranscriptionResult:
    model = _get_model()
    # vad_filter runs faster-whisper's built-in Silero VAD over the audio before
    # decoding, dropping silence/noise stretches. Without it, Whisper still "confidently"
    # invents plausible-sounding text for non-speech audio (comfort noise from a muted
    # call, background hiss) instead of returning nothing.
    segments, _ = model.transcribe(audio, language="en", vad_filter=True)
    materialized = list(segments)
    text_segments = [
        (segment, segment.text.strip())
        for segment in materialized
        if segment.text.strip()
    ]
    if not text_segments:
        no_speech_probability = max(
            (float(getattr(segment, "no_speech_prob", 1.0)) for segment in materialized),
            default=1.0,
        )
        return TranscriptionResult("", 0.0, no_speech_probability)

    weights = [
        max(float(segment.end) - float(segment.start), 0.01)
        for segment, _ in text_segments
    ]
    total_weight = sum(weights)
    average_log_probability = sum(
        float(getattr(segment, "avg_logprob", -1.0)) * weight
        for (segment, _), weight in zip(text_segments, weights)
    ) / total_weight
    confidence = min(max(math.exp(average_log_probability), 0.0), 1.0)
    no_speech_probability = sum(
        float(getattr(segment, "no_speech_prob", 0.0)) * weight
        for (segment, _), weight in zip(text_segments, weights)
    ) / total_weight
    text = " ".join(text for _, text in text_segments)
    return TranscriptionResult(text, confidence, no_speech_probability)


def transcribe(audio: np.ndarray, sample_rate: int = 16000) -> str:
    return transcribe_with_metadata(audio, sample_rate).text


def preload() -> None:
    _get_model()
