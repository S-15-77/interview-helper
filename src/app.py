import queue
import signal
import sys
import threading
import traceback
from pathlib import Path

import numpy as np
import pyaudio
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from src.audio_capture import (
    FRAME_SIZE,
    SAMPLE_RATE,
    UtteranceSegmenter,
    find_device_index,
    open_capture_stream,
)
from src.llm_client import preload as preload_llm
from src.llm_client import stream_answer
from src.overlay import OverlayWindow
from src.session_logger import SessionLogger
from src.transcriber import preload as preload_transcriber
from src.transcriber import transcribe

CONTEXT_WORD_LIMIT = 200


def pcm_bytes_to_float32(data: bytes) -> np.ndarray:
    ints = np.frombuffer(data, dtype="<i2")
    return ints.astype(np.float32) / 32768.0


def trim_context(context: str, new_text: str, word_limit: int = CONTEXT_WORD_LIMIT) -> str:
    words = (context + " " + new_text).split()
    return " ".join(words[-word_limit:])


class Worker(threading.Thread):
    def __init__(self, utterance_queue: "queue.Queue[tuple[bytes, bool]]", overlay: OverlayWindow, logger: SessionLogger):
        super().__init__(daemon=True)
        self.utterance_queue = utterance_queue
        self.overlay = overlay
        self.logger = logger
        self.context = ""
        self.current_filler = ""
        self._partial_thread = None

    def _process_partial(self, audio: np.ndarray):
        try:
            partial_question = transcribe(audio, SAMPLE_RATE)
            if partial_question.strip():
                from src.llm_client import generate_filler
                filler = generate_filler(partial_question)
                self.current_filler = filler
        except Exception as e:
            print(f"Partial transcription error: {e}")

    def run(self):
        while True:
            pcm_bytes, is_final = self.utterance_queue.get()
            try:
                audio = pcm_bytes_to_float32(pcm_bytes)
                
                if not is_final:
                    self.current_filler = ""
                    self._partial_thread = threading.Thread(target=self._process_partial, args=(audio,), daemon=True)
                    self._partial_thread.start()
                    continue
                    
                question = transcribe(audio, SAMPLE_RATE)
                if not question.strip():
                    self.current_filler = ""
                    continue

                self.overlay.begin_question(question)
                if self.current_filler:
                    self.overlay.append_text(f"<i>{self.current_filler}</i>\n\n")
                    self.current_filler = ""
                    
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
            except Exception:
                traceback.print_exc()


class CaptureThread(threading.Thread):
    def __init__(
        self,
        utterance_queue: "queue.Queue[tuple[bytes, bool]]",
        pa: pyaudio.PyAudio,
        device_index: int,
        overlay: OverlayWindow,
    ):
        super().__init__(daemon=True)
        self.utterance_queue = utterance_queue
        self.pa = pa
        self.device_index = device_index
        self.overlay = overlay
        self._stop = threading.Event()

    def run(self):
        pa = self.pa
        try:
            stream = open_capture_stream(pa, self.device_index)
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
        except Exception as exc:
            self.overlay.show_error(f"Audio capture stopped: {exc}")

    def stop(self):
        self._stop.set()


def main():
    pa = pyaudio.PyAudio()
    try:
        device_index = find_device_index(pa)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)

    _signal_timer = QTimer()
    _signal_timer.timeout.connect(lambda: None)
    _signal_timer.start(200)

    overlay = OverlayWindow()
    overlay.show()

    preload_transcriber()
    preload_llm()

    logger = SessionLogger(Path("sessions"))
    utterance_queue: "queue.Queue[tuple[bytes, bool]]" = queue.Queue()

    worker = Worker(utterance_queue, overlay, logger)
    worker.start()

    capture = CaptureThread(utterance_queue, pa, device_index, overlay)
    capture.start()

    def handle_sigint(*_args):
        # Without this, Ctrl+C's default handler raises KeyboardInterrupt
        # from inside whatever Qt slot happens to be running when the
        # signal is noticed (here, the timer below) — PyQt6 treats any
        # exception escaping a slot as fatal and calls abort(). Stop the
        # audio stream deterministically first, then quit Qt normally
        # instead of letting a KeyboardInterrupt raise at all.
        capture.stop()
        capture.join(timeout=2)
        app.quit()

    signal.signal(signal.SIGINT, handle_sigint)
    overlay.quit_requested.connect(handle_sigint)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
