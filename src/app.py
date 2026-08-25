import queue
import signal
import sys
import threading
import traceback
from dataclasses import dataclass
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
from src.llm_client import list_application_profiles, stream_answer
from src.overlay import OverlayWindow
from src.session_logger import SessionLogger
from src.transcriber import preload as preload_transcriber
from src.transcriber import transcribe

CONTEXT_WORD_LIMIT = 200


@dataclass(frozen=True)
class ManualQuestion:
    text: str


WorkItem = tuple[bytes, bool] | ManualQuestion | None


def pcm_bytes_to_float32(data: bytes) -> np.ndarray:
    ints = np.frombuffer(data, dtype="<i2")
    return ints.astype(np.float32) / 32768.0


def trim_context(context: str, new_text: str, word_limit: int = CONTEXT_WORD_LIMIT) -> str:
    words = (context + " " + new_text).split()
    return " ".join(words[-word_limit:])


class Worker(threading.Thread):
    def __init__(
        self,
        utterance_queue: "queue.Queue[WorkItem]",
        overlay: OverlayWindow,
        logger: SessionLogger,
    ):
        super().__init__(daemon=True)
        self.utterance_queue = utterance_queue
        self.overlay = overlay
        self.logger = logger
        self.context = ""
        self.current_filler = ""
        self._partial_thread: threading.Thread | None = None
        self._partial_generation = 0
        self._partial_lock = threading.Lock()
        self._profile_name: str | None = None
        self._profile_lock = threading.Lock()

    def _process_partial(self, audio: np.ndarray, generation: int):
        try:
            partial_question = transcribe(audio, SAMPLE_RATE)
            if partial_question.strip():
                from src.llm_client import generate_filler

                filler = generate_filler(partial_question)
                with self._partial_lock:
                    # The final utterance may have arrived while transcription or
                    # generation was running. Never let that stale result leak into
                    # the next question.
                    if generation == self._partial_generation:
                        self.current_filler = filler
        except Exception as e:
            print(f"Partial transcription error: {e}")

    def _start_partial(self, audio: np.ndarray) -> None:
        with self._partial_lock:
            # One useful filler is enough. Re-transcribing every cumulative partial
            # wastes CPU and can slow down the final answer.
            if self.current_filler or (
                self._partial_thread is not None and self._partial_thread.is_alive()
            ):
                return
            self._partial_generation += 1
            generation = self._partial_generation
            thread = threading.Thread(
                target=self._process_partial,
                args=(audio, generation),
                daemon=True,
            )
            self._partial_thread = thread
        thread.start()

    def _take_current_filler(self) -> str:
        with self._partial_lock:
            # Invalidate any in-flight partial before processing the final audio.
            self._partial_generation += 1
            filler = self.current_filler
            self.current_filler = ""
            self._partial_thread = None
            return filler

    def stop(self) -> None:
        with self._partial_lock:
            self._partial_generation += 1
            self.current_filler = ""
        self.utterance_queue.put(None)

    def submit_manual_question(self, question: str) -> None:
        question = question.strip()
        if question:
            self.utterance_queue.put(ManualQuestion(question))

    def set_profile(self, profile_name: str | None) -> None:
        with self._profile_lock:
            self._profile_name = profile_name or None
            # Conversation from one application should never bias another.
            self.context = ""

    def _prompt_state(self) -> tuple[str, str | None]:
        with self._profile_lock:
            return self.context, self._profile_name

    def _answer_question(self, question: str, filler: str = "") -> None:
        self.overlay.begin_question(question)
        if filler:
            self.overlay.append_text(f"{filler}\n\n")

        context, profile_name = self._prompt_state()
        try:
            answer_parts = []
            for chunk in stream_answer(
                question,
                context,
                profile_name=profile_name,
            ):
                answer_parts.append(chunk)
                self.overlay.append_text(chunk)
        except Exception as exc:
            self.overlay.show_error(f"Ollama error: {exc}")
            return

        answer = "".join(answer_parts)
        with self._profile_lock:
            if profile_name == self._profile_name:
                self.context = trim_context(
                    self.context,
                    f"Q: {question} A: {answer}",
                )
        self.logger.log(question, answer)

    def run(self):
        while True:
            item = self.utterance_queue.get()
            if item is None:
                return
            if isinstance(item, ManualQuestion):
                try:
                    self._take_current_filler()
                    self._answer_question(item.text)
                except Exception:
                    traceback.print_exc()
                continue
            pcm_bytes, is_final = item
            try:
                audio = pcm_bytes_to_float32(pcm_bytes)

                if not is_final:
                    self._start_partial(audio)
                    continue

                filler = self._take_current_filler()
                question = transcribe(audio, SAMPLE_RATE)
                if not question.strip():
                    continue

                self._answer_question(question, filler)
            except Exception:
                traceback.print_exc()


class CaptureThread(threading.Thread):
    def __init__(
        self,
        utterance_queue: "queue.Queue[WorkItem]",
        pa: pyaudio.PyAudio,
        device_index: int,
        overlay: OverlayWindow,
    ):
        super().__init__(daemon=True)
        self.utterance_queue = utterance_queue
        self.pa = pa
        self.device_index = device_index
        self.overlay = overlay
        # threading.Thread already owns a private _stop() method used by join().
        # Shadowing it with an Event makes a completed capture thread unjoinable.
        self._stop_event = threading.Event()

    def run(self):
        pa = self.pa
        stream = None
        try:
            stream = open_capture_stream(pa, self.device_index)
            segmenter = UtteranceSegmenter()
            while not self._stop_event.is_set():
                frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
                utterance = segmenter.push_frame(frame)
                if utterance is not None:
                    self.utterance_queue.put(utterance)
        except Exception as exc:
            self.overlay.show_error(f"Audio capture stopped: {exc}")
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            pa.terminate()

    def stop(self):
        self._stop_event.set()


def main():
    pa = pyaudio.PyAudio()
    try:
        device_index = find_device_index(pa)
    except RuntimeError as exc:
        pa.terminate()
        print(exc, file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)

    _signal_timer = QTimer()
    _signal_timer.timeout.connect(lambda: None)
    _signal_timer.start(200)

    overlay = OverlayWindow(list_application_profiles())
    overlay.show()

    logger = SessionLogger(Path("sessions"))
    utterance_queue: "queue.Queue[WorkItem]" = queue.Queue()

    worker = Worker(utterance_queue, overlay, logger)
    worker.set_profile(overlay.selected_profile())
    overlay.manual_question_submitted.connect(worker.submit_manual_question)
    overlay.profile_changed.connect(worker.set_profile)
    capture = CaptureThread(utterance_queue, pa, device_index, overlay)
    startup_cancelled = threading.Event()
    shutdown_started = threading.Event()
    lifecycle_lock = threading.Lock()

    def initialize_services():
        try:
            overlay.show_status("Loading speech model…")
            preload_transcriber()
            if startup_cancelled.is_set():
                return

            overlay.show_status("Loading language model…")
            preload_llm()
            if startup_cancelled.is_set():
                return

            # Starting and stopping share this lock so closing the app during
            # initialization cannot start capture on an already-terminated
            # PyAudio instance.
            with lifecycle_lock:
                if startup_cancelled.is_set():
                    return
                worker.start()
                capture.start()
            overlay.show_status("Listening…")
        except Exception as exc:
            if not startup_cancelled.is_set():
                pa.terminate()
                overlay.show_error(f"Startup failed: {exc}")

    startup_thread = threading.Thread(target=initialize_services, daemon=True)
    startup_thread.start()

    def handle_sigint(*_args):
        if shutdown_started.is_set():
            return
        shutdown_started.set()
        startup_cancelled.set()
        # Without this, Ctrl+C's default handler raises KeyboardInterrupt
        # from inside whatever Qt slot happens to be running when the
        # signal is noticed (here, the timer below) — PyQt6 treats any
        # exception escaping a slot as fatal and calls abort(). Stop the
        # audio stream deterministically first, then quit Qt normally
        # instead of letting a KeyboardInterrupt raise at all.
        with lifecycle_lock:
            capture.stop()
            capture_was_started = capture.ident is not None
            worker_was_started = worker.ident is not None
            if worker_was_started:
                worker.stop()
            if not capture_was_started:
                pa.terminate()
        if capture.is_alive():
            capture.join(timeout=2)
        if worker.is_alive():
            worker.join(timeout=1)
        app.quit()

    signal.signal(signal.SIGINT, handle_sigint)
    overlay.quit_requested.connect(handle_sigint)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
