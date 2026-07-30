import sys
import warnings

import pyaudio

with warnings.catch_warnings():
    # webrtcvad's own import path pulls in pkg_resources, which emits this
    # deprecation notice on every startup; harmless, so mute it at the source
    # instead of letting it print each run.
    warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
    import webrtcvad

FRAME_MS = 30
SAMPLE_RATE = 16000
FRAME_SIZE = int(SAMPLE_RATE * FRAME_MS / 1000)
SILENCE_TRAILING_MS = 1000
SILENCE_TRAILING_FRAMES = SILENCE_TRAILING_MS // FRAME_MS
# Below this, a "speech" burst is more likely a click/comfort-noise blip than a real
# word — Whisper hallucinates confident text on exactly these short noise fragments.
MIN_SPEECH_MS = 300
MIN_SPEECH_FRAMES = MIN_SPEECH_MS // FRAME_MS


class UtteranceSegmenter:
    def __init__(self, vad_aggressiveness: int = 3):
        self._vad = webrtcvad.Vad(vad_aggressiveness)
        self._speech_frames: list[bytes] = []
        self._trailing_silence = 0

    def push_frame(self, frame_bytes: bytes) -> bytes | None:
        is_speech = self._vad.is_speech(frame_bytes, SAMPLE_RATE)

        if is_speech:
            self._speech_frames.append(frame_bytes)
            self._trailing_silence = 0
            return None

        if not self._speech_frames:
            return None

        self._trailing_silence += 1
        if self._trailing_silence < SILENCE_TRAILING_FRAMES:
            return None

        frames, self._speech_frames = self._speech_frames, []
        self._trailing_silence = 0
        if len(frames) < MIN_SPEECH_FRAMES:
            return None
        return b"".join(frames)


def find_device_index(pa: pyaudio.PyAudio, name_substring: str = "BlackHole") -> int:
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if name_substring.lower() in info["name"].lower() and info["maxInputChannels"] > 0:
            return i
    available = [pa.get_device_info_by_index(i)["name"] for i in range(pa.get_device_count())]
    raise RuntimeError(
        f"No input device matching '{name_substring}' found. Available devices: {available}"
    )


def open_capture_stream(pa: pyaudio.PyAudio, device_index: int) -> pyaudio.Stream:
    return pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=FRAME_SIZE,
    )


def _manual_check():
    pa = pyaudio.PyAudio()
    try:
        device_index = find_device_index(pa)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    print(f"Reading from device index {device_index} for 5 seconds...")
    stream = open_capture_stream(pa, device_index)
    frame_count = 0
    for _ in range(int(5000 / FRAME_MS)):
        stream.read(FRAME_SIZE, exception_on_overflow=False)
        frame_count += 1
    stream.stop_stream()
    stream.close()
    pa.terminate()
    print(f"Captured {frame_count} frames successfully.")


if __name__ == "__main__":
    _manual_check()
