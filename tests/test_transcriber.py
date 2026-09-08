import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest
import soundfile as sf

from src.transcriber import TranscriptionResult, transcribe, transcribe_with_metadata

FIXTURES = Path(__file__).parent / "fixtures"


def test_transcribe_recognizes_known_speech():
    audio, sample_rate = sf.read(str(FIXTURES / "hello.wav"), dtype="float32")
    assert sample_rate == 16000

    text = transcribe(audio, sample_rate)

    assert "hello" in text.lower()


def test_transcription_metadata_uses_duration_weighted_segment_scores():
    model = Mock()
    model.transcribe.return_value = (
        iter(
            [
                SimpleNamespace(
                    text=" What is",
                    start=0.0,
                    end=1.0,
                    avg_logprob=-0.2,
                    no_speech_prob=0.1,
                ),
                SimpleNamespace(
                    text=" IR? ",
                    start=1.0,
                    end=3.0,
                    avg_logprob=-0.5,
                    no_speech_prob=0.4,
                ),
            ]
        ),
        Mock(),
    )

    with patch("src.transcriber._get_model", return_value=model):
        result = transcribe_with_metadata(np.zeros(100, dtype=np.float32))

    assert result.text == "What is IR?"
    assert result.confidence == pytest.approx(math.exp(-0.4))
    assert result.no_speech_probability == pytest.approx(0.3)
    assert result.is_reliable


def test_empty_transcription_is_unreliable():
    model = Mock()
    model.transcribe.return_value = (iter([]), Mock())

    with patch("src.transcriber._get_model", return_value=model):
        result = transcribe_with_metadata(np.zeros(100, dtype=np.float32))

    assert result == TranscriptionResult("", 0.0, 1.0)
    assert not result.is_reliable


def test_low_log_probability_or_high_no_speech_probability_is_unreliable():
    assert not TranscriptionResult("Question", 0.1, 0.05).is_reliable
    assert not TranscriptionResult("Question", 0.9, 0.9).is_reliable


def test_transcriber_uses_configured_model_and_automatic_language():
    model = Mock()
    model.transcribe.return_value = (iter([]), Mock())

    with patch("src.transcriber._get_model", return_value=model) as get_model:
        transcribe_with_metadata(
            np.zeros(100, dtype=np.float32),
            model_name="small.en",
            language="auto",
        )

    get_model.assert_called_once_with("small.en")
    model.transcribe.assert_called_once()
    args, kwargs = model.transcribe.call_args
    assert np.array_equal(args[0], np.zeros(100, dtype=np.float32))
    assert kwargs == {"language": None, "vad_filter": True}
