import webrtcvad

FRAME_MS = 30
SAMPLE_RATE = 16000
FRAME_SIZE = int(SAMPLE_RATE * FRAME_MS / 1000)
SILENCE_TRAILING_MS = 1000
SILENCE_TRAILING_FRAMES = SILENCE_TRAILING_MS // FRAME_MS


class UtteranceSegmenter:
    def __init__(self, vad_aggressiveness: int = 2):
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

        utterance = b"".join(self._speech_frames)
        self._speech_frames = []
        self._trailing_silence = 0
        return utterance
