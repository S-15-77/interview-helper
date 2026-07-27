from pathlib import Path

import soundfile as sf

from src.audio_capture import FRAME_SIZE, SAMPLE_RATE, UtteranceSegmenter

FIXTURES = Path(__file__).parent / "fixtures"


def _pcm_bytes(frame):
    ints = (frame * 32767).astype("<i2")
    return ints.tobytes()


def _frames(audio, frame_size):
    for start in range(0, len(audio) - frame_size + 1, frame_size):
        yield audio[start:start + frame_size]


def test_segmenter_finalizes_utterance_after_trailing_silence():
    audio, sample_rate = sf.read(str(FIXTURES / "hello.wav"), dtype="float32")
    assert sample_rate == SAMPLE_RATE

    segmenter = UtteranceSegmenter()
    for frame in _frames(audio, FRAME_SIZE):
        segmenter.push_frame(_pcm_bytes(frame))

    silence_frame = b"\x00\x00" * FRAME_SIZE
    utterance = None
    for _ in range(40):  # 40 * 30ms = 1200ms of silence
        result = segmenter.push_frame(silence_frame)
        if result is not None:
            utterance = result
            break

    assert utterance is not None
    assert len(utterance) > 0


def test_segmenter_ignores_leading_silence():
    segmenter = UtteranceSegmenter()
    silence_frame = b"\x00\x00" * FRAME_SIZE

    for _ in range(10):
        assert segmenter.push_frame(silence_frame) is None
