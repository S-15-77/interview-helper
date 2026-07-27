from pathlib import Path

import soundfile as sf

from src.transcriber import transcribe

FIXTURES = Path(__file__).parent / "fixtures"


def test_transcribe_recognizes_known_speech():
    audio, sample_rate = sf.read(str(FIXTURES / "hello.wav"), dtype="float32")
    assert sample_rate == 16000

    text = transcribe(audio, sample_rate)

    assert "hello" in text.lower()
