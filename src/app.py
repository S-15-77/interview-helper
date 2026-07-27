import queue
import sys
import threading
from pathlib import Path

import numpy as np
import pyaudio
from PyQt6.QtWidgets import QApplication

from src.audio_capture import (
    FRAME_SIZE,
    SAMPLE_RATE,
    UtteranceSegmenter,
    find_device_index,
    open_capture_stream,
)
from src.llm_client import stream_answer
from src.overlay import OverlayWindow
from src.session_logger import SessionLogger
from src.transcriber import transcribe

CONTEXT_WORD_LIMIT = 200


def pcm_bytes_to_float32(data: bytes) -> np.ndarray:
    ints = np.frombuffer(data, dtype="<i2")
    return ints.astype(np.float32) / 32768.0


def trim_context(context: str, new_text: str, word_limit: int = CONTEXT_WORD_LIMIT) -> str:
    words = (context + " " + new_text).split()
    return " ".join(words[-word_limit:])


class Worker(threading.Thread):
    def __init__(self, utterance_queue: "queue.Queue[bytes]", overlay: OverlayWindow, logger: SessionLogger):
        super().__init__(daemon=True)
        self.utterance_queue = utterance_queue
        self.overlay = overlay
        self.logger = logger
        self.context = ""

    def run(self):
        while True:
            pcm_bytes = self.utterance_queue.get()
            audio = pcm_bytes_to_float32(pcm_bytes)
            question = transcribe(audio, SAMPLE_RATE)
            if not question.strip():
                continue

            self.overlay.clear()
            try:
                answer_parts = []
                for chunk in stream_answer(question, self.context):
                    answer_parts.append(chunk)
                    self.overlay.append_text(chunk)
            except Exception as exc:
                self.overlay.show_error(f"Ollama error: {exc}")
                continue

            answer = "".join(answer_parts)
            self.context = trim_context(self.context, f"Q: {question} A: {answer}")
            self.logger.log(question, answer)


class CaptureThread(threading.Thread):
    def __init__(self, utterance_queue: "queue.Queue[bytes]"):
        super().__init__(daemon=True)
        self.utterance_queue = utterance_queue
        self._stop = threading.Event()

    def run(self):
        pa = pyaudio.PyAudio()
        device_index = find_device_index(pa)
        stream = open_capture_stream(pa, device_index)
        segmenter = UtteranceSegmenter()
        try:
            while not self._stop.is_set():
                frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
                utterance = segmenter.push_frame(frame)
                if utterance is not None:
                    self.utterance_queue.put(utterance)
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def stop(self):
        self._stop.set()


def main():
    app = QApplication(sys.argv)
    overlay = OverlayWindow()
    overlay.show()

    logger = SessionLogger(Path("sessions"))
    utterance_queue: "queue.Queue[bytes]" = queue.Queue()

    worker = Worker(utterance_queue, overlay, logger)
    worker.start()

    capture = CaptureThread(utterance_queue)
    capture.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
