from pathlib import Path

import pytest
import soundfile as sf

from src.audio_capture import FRAME_SIZE, SAMPLE_RATE, UtteranceSegmenter, find_device_index

FIXTURES = Path(__file__).parent / "fixtures"


class _FakePyAudio:
    def __init__(self, devices):
        self._devices = devices

    def get_device_count(self):
        return len(self._devices)

    def get_device_info_by_index(self, i):
        return self._devices[i]


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
    result = None
    for _ in range(40):  # 40 * 30ms = 1200ms of silence
        result = segmenter.push_frame(silence_frame)
        if result is not None:
            break

    assert result is not None
    utterance, is_final = result
    assert is_final is True
    assert len(utterance) > 0


def test_segmenter_ignores_leading_silence():
    segmenter = UtteranceSegmenter()
    silence_frame = b"\x00\x00" * FRAME_SIZE

    for _ in range(10):
        assert segmenter.push_frame(silence_frame) is None


def test_segmenter_emits_non_final_partial_during_continuous_speech():
    audio, sample_rate = sf.read(str(FIXTURES / "hello.wav"), dtype="float32")
    assert sample_rate == SAMPLE_RATE

    # Small partial_ms so a real speech fixture crosses the threshold before finalizing.
    segmenter = UtteranceSegmenter(partial_ms=90)  # 3 frames of continuous speech
    partials = [
        result
        for frame in _frames(audio, FRAME_SIZE)
        if (result := segmenter.push_frame(_pcm_bytes(frame))) is not None
    ]

    assert partials, "expected at least one partial chunk before finalization"
    for chunk, is_final in partials:
        assert is_final is False
        assert len(chunk) > 0


def test_find_device_index_matches_by_substring_case_insensitively():
    pa = _FakePyAudio([
        {"name": "MacBook Pro Microphone", "maxInputChannels": 1},
        {"name": "BlackHole 2ch", "maxInputChannels": 2},
    ])

    assert find_device_index(pa) == 1


def test_find_device_index_skips_output_only_devices():
    pa = _FakePyAudio([
        {"name": "BlackHole 2ch", "maxInputChannels": 0},  # output side of the device
        {"name": "BlackHole 2ch", "maxInputChannels": 2},
    ])

    assert find_device_index(pa) == 1


def test_find_device_index_raises_when_no_match():
    pa = _FakePyAudio([{"name": "MacBook Pro Microphone", "maxInputChannels": 1}])

    with pytest.raises(RuntimeError):
        find_device_index(pa)
