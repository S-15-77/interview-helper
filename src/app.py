import re
import signal
import sys
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pyaudio
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from src.audio_capture import (
    FRAME_SIZE,
    SAMPLE_RATE,
    UtteranceSegmenter,
    open_capture_stream,
)
from src.llm_client import DEFAULT_MODEL, DEFAULT_OLLAMA_BASE_URL
from src.llm_client import preload as preload_llm
from src.llm_client import list_application_profiles, stream_answer
from src.overlay import OverlayWindow
from src.session_logger import SessionLogger
from src.settings import AppSettings, SettingsError, load_settings
from src.setup_window import SetupWindow
from src.transcriber import preload as preload_transcriber
from src.transcriber import transcribe, transcribe_with_metadata

CONTEXT_WORD_LIMIT = 200
WORK_QUEUE_MAXSIZE = 3
DUPLICATE_QUESTION_WINDOW_SECONDS = 20.0


@dataclass(frozen=True)
class ManualQuestion:
    text: str
    source: str = "manual"
    context_override: str | None = None
    response_style: str | None = None


@dataclass(frozen=True)
class AudioWork:
    pcm_bytes: bytes
    is_final: bool
    captured_at: float


@dataclass(frozen=True)
class RetryTranscription:
    audio: AudioWork


@dataclass(frozen=True)
class LastAnswerRequest:
    question: str
    context: str
    profile_name: str | None


WorkItem = AudioWork | ManualQuestion | RetryTranscription


class WorkQueue:
    """A bounded queue where explicit and recent work wins over stale audio."""

    def __init__(self, maxsize: int = WORK_QUEUE_MAXSIZE):
        if maxsize <= 0:
            raise ValueError("maxsize must be greater than zero")
        self.maxsize = maxsize
        self._items: deque[WorkItem] = deque()
        self._condition = threading.Condition()
        self._stopped = False
        self._supersede_callback: Callable[[], None] | None = None

    def set_supersede_callback(self, callback: Callable[[], None]) -> None:
        self._supersede_callback = callback

    def _submit_priority(self, item: ManualQuestion | RetryTranscription) -> bool:
        with self._condition:
            if self._stopped:
                return False
        # Cancel before publishing the replacement item. If notification came
        # first, the worker could start this new manual question and then have
        # the callback accidentally cancel the very work it was meant to favor.
        if self._supersede_callback is not None:
            self._supersede_callback()
        with self._condition:
            if self._stopped:
                return False
            # An explicit question, correction, or retry removes older queued work
            # so it cannot sit invisibly behind captured call audio.
            self._items.clear()
            self._items.append(item)
            self._condition.notify()
        return True

    def submit_manual(self, question: ManualQuestion) -> bool:
        return self._submit_priority(question)

    def submit_retry(self, retry: RetryTranscription) -> bool:
        return self._submit_priority(retry)

    def submit_audio(self, audio: AudioWork) -> bool:
        with self._condition:
            if self._stopped:
                return False
            if any(
                isinstance(item, (ManualQuestion, RetryTranscription))
                for item in self._items
            ):
                return False

            if audio.is_final:
                # A final utterance makes every older queued partial/final audio
                # stale. Keep the newest one without ever blocking capture.
                self._items = deque(
                    item
                    for item in self._items
                    if isinstance(item, (ManualQuestion, RetryTranscription))
                )
            else:
                if any(
                    isinstance(item, AudioWork) and item.is_final
                    for item in self._items
                ):
                    return False
                # Partials are cumulative, so only the newest partial is useful.
                self._items = deque(
                    item
                    for item in self._items
                    if not isinstance(item, AudioWork) or item.is_final
                )

            if len(self._items) >= self.maxsize:
                return False
            self._items.append(audio)
            self._condition.notify()
            return True

    def get(self) -> WorkItem | None:
        with self._condition:
            while not self._items and not self._stopped:
                self._condition.wait()
            if self._stopped:
                return None
            return self._items.popleft()

    def clear(self) -> None:
        with self._condition:
            self._items.clear()

    def discard_audio(self) -> None:
        with self._condition:
            self._items = deque(
                item for item in self._items if isinstance(item, ManualQuestion)
            )

    def stop(self) -> None:
        with self._condition:
            self._stopped = True
            self._items.clear()
            self._condition.notify_all()

    def qsize(self) -> int:
        with self._condition:
            return len(self._items)


def normalize_question(question: str) -> str:
    return " ".join(re.findall(r"\w+", question.casefold()))


def pcm_bytes_to_float32(data: bytes) -> np.ndarray:
    ints = np.frombuffer(data, dtype="<i2")
    return ints.astype(np.float32) / 32768.0


def trim_context(context: str, new_text: str, word_limit: int = CONTEXT_WORD_LIMIT) -> str:
    words = (context + " " + new_text).split()
    return " ".join(words[-word_limit:])


class Worker(threading.Thread):
    def __init__(
        self,
        work_queue: WorkQueue,
        overlay: OverlayWindow,
        logger: SessionLogger,
        *,
        ollama_model: str = DEFAULT_MODEL,
        ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
        whisper_model: str = "base.en",
        whisper_language: str = "en",
        default_response_style: str = "default",
    ):
        super().__init__(daemon=True)
        self.work_queue = work_queue
        self.overlay = overlay
        self.logger = logger
        self.ollama_model = ollama_model
        self.ollama_base_url = ollama_base_url
        self.whisper_model = whisper_model
        self.whisper_language = whisper_language
        self.default_response_style = default_response_style
        self.context = ""
        self.current_filler = ""
        self._partial_thread: threading.Thread | None = None
        self._partial_generation = 0
        self._partial_lock = threading.Lock()
        self._profile_name: str | None = None
        self._profile_lock = threading.Lock()
        self._operation_lock = threading.Lock()
        self._active_cancel_event: threading.Event | None = None
        self._last_audio_question: tuple[str, float] | None = None
        self._last_audio_lock = threading.Lock()
        self._last_audio_work: AudioWork | None = None
        self._last_answer_lock = threading.Lock()
        self._last_answer_request: LastAnswerRequest | None = None
        self._listening_paused = threading.Event()
        self.work_queue.set_supersede_callback(self._cancel_active_operation)

    def _process_partial(self, audio: np.ndarray, generation: int):
        try:
            transcription_options = {}
            if self.whisper_model != "base.en":
                transcription_options["model_name"] = self.whisper_model
            if self.whisper_language != "en":
                transcription_options["language"] = self.whisper_language
            partial_question = transcribe(
                audio,
                SAMPLE_RATE,
                **transcription_options,
            )
            if partial_question.strip():
                from src.llm_client import generate_filler

                filler = generate_filler(
                    partial_question,
                    model=self.ollama_model,
                    base_url=self.ollama_base_url,
                )
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
        self._cancel_active_operation()
        self.work_queue.stop()

    def _begin_operation(self) -> threading.Event:
        cancel_event = threading.Event()
        with self._operation_lock:
            self._active_cancel_event = cancel_event
        return cancel_event

    def _finish_operation(self, cancel_event: threading.Event) -> None:
        with self._operation_lock:
            if self._active_cancel_event is cancel_event:
                self._active_cancel_event = None

    def _cancel_active_operation(self) -> bool:
        with self._operation_lock:
            if self._active_cancel_event is None:
                return False
            self._active_cancel_event.set()
            return True

    def cancel_current(self) -> None:
        self.work_queue.clear()
        cancelled = self._cancel_active_operation()
        self._take_current_filler()
        self.overlay.show_status("Cancelling…" if cancelled else self._idle_status())

    def _idle_status(self, detail: str | None = None) -> str:
        base = "Paused" if self._listening_paused.is_set() else "Listening"
        return f"{base} • {detail}" if detail else f"{base}…"

    def set_listening_paused(self, paused: bool) -> None:
        if paused:
            self._listening_paused.set()
            self.work_queue.discard_audio()
        else:
            self._listening_paused.clear()
        with self._operation_lock:
            operation_active = self._active_cancel_event is not None
        if not operation_active:
            self.overlay.show_status(self._idle_status())

    def submit_manual_question(self, question: str) -> None:
        question = question.strip()
        if question:
            if self.work_queue.submit_manual(ManualQuestion(question)):
                self.overlay.show_status("Manual question queued…")

    def submit_transcript_correction(self, question: str) -> None:
        question = question.strip()
        if question:
            corrected = ManualQuestion(question, source="correction")
            if self.work_queue.submit_manual(corrected):
                self.overlay.show_status("Corrected question queued…")

    def regenerate_last_answer(self, response_style: str | None = None) -> None:
        with self._last_answer_lock:
            previous = self._last_answer_request
        if previous is None:
            self.overlay.show_status(self._idle_status("no answer to regenerate"))
            return
        selected_style = response_style or self.default_response_style
        request = ManualQuestion(
            previous.question,
            source="regenerate" if response_style is None else selected_style,
            context_override=previous.context,
            response_style=selected_style,
        )
        if self.work_queue.submit_manual(request):
            label = {
                "default": "Regenerating answer…",
                "shorter": "Generating shorter answer…",
                "more_detail": "Generating detailed answer…",
            }.get(selected_style, "Regenerating answer…")
            self.overlay.show_status(label)

    def retry_last_transcription(self) -> None:
        with self._last_audio_lock:
            audio = self._last_audio_work
        if audio is None:
            self.overlay.show_status(self._idle_status("no transcript to retry"))
            return
        if self.work_queue.submit_retry(RetryTranscription(audio)):
            self.overlay.show_status("Retrying transcription…")

    def set_profile(self, profile_name: str | None) -> None:
        with self._profile_lock:
            self._profile_name = profile_name or None
            # Conversation from one application should never bias another.
            self.context = ""
        with self._last_answer_lock:
            self._last_answer_request = None

    def _prompt_state(self) -> tuple[str, str | None]:
        with self._profile_lock:
            return self.context, self._profile_name

    def _is_duplicate_audio_question(self, question: str, captured_at: float) -> bool:
        normalized = normalize_question(question)
        if not normalized:
            return False
        previous = self._last_audio_question
        self._last_audio_question = (normalized, captured_at)
        if previous is None:
            return False
        previous_question, previous_captured_at = previous
        age = captured_at - previous_captured_at
        return (
            normalized == previous_question
            and 0 <= age <= DUPLICATE_QUESTION_WINDOW_SECONDS
        )

    def _answer_question(
        self,
        question: str,
        filler: str = "",
        *,
        cancel_event: threading.Event | None = None,
        operation_started: float | None = None,
        transcription_seconds: float = 0.0,
        source: str = "manual",
        context_override: str | None = None,
        response_style: str | None = None,
    ) -> None:
        owns_operation = cancel_event is None
        cancel_event = cancel_event or self._begin_operation()
        operation_started = operation_started or time.perf_counter()
        if cancel_event.is_set():
            if owns_operation:
                self._finish_operation(cancel_event)
            return

        selected_style = response_style or self.default_response_style
        self.overlay.begin_question(question)
        if filler:
            self.overlay.append_text(f"{filler}\n\n")
        self.overlay.show_status("Generating…")

        context, profile_name = self._prompt_state()
        if context_override is not None:
            context = context_override
        with self._last_answer_lock:
            self._last_answer_request = LastAnswerRequest(
                question,
                context,
                profile_name,
            )
        generation_started = time.perf_counter()
        first_token_seconds: float | None = None
        answer_parts = []
        answer_stream = None
        try:
            generation_options = {
                "profile_name": profile_name,
                "response_style": selected_style,
            }
            if self.ollama_model != DEFAULT_MODEL:
                generation_options["model"] = self.ollama_model
            if self.ollama_base_url != DEFAULT_OLLAMA_BASE_URL:
                generation_options["base_url"] = self.ollama_base_url
            answer_stream = stream_answer(
                question,
                context,
                **generation_options,
            )
            for chunk in answer_stream:
                if cancel_event.is_set():
                    break
                if first_token_seconds is None:
                    first_token_seconds = time.perf_counter() - generation_started
                answer_parts.append(chunk)
                self.overlay.append_text(chunk)
        except Exception as exc:
            if not cancel_event.is_set():
                self.overlay.show_error(f"Ollama error: {exc}")
                self.overlay.show_status(self._idle_status())
            return
        finally:
            close_stream = getattr(answer_stream, "close", None)
            if close_stream is not None:
                close_stream()
            if owns_operation:
                self._finish_operation(cancel_event)

        if cancel_event.is_set():
            self.overlay.show_cancelled()
            self.overlay.show_status(self._idle_status("answer cancelled"))
            return

        answer = "".join(answer_parts)
        generation_seconds = time.perf_counter() - generation_started
        total_seconds = time.perf_counter() - operation_started
        timings = {
            "source": source,
            "transcription_ms": round(transcription_seconds * 1000),
            "first_token_ms": (
                round(first_token_seconds * 1000)
                if first_token_seconds is not None
                else None
            ),
            "generation_ms": round(generation_seconds * 1000),
            "total_ms": round(total_seconds * 1000),
        }
        with self._profile_lock:
            if profile_name == self._profile_name:
                self.context = trim_context(
                    self.context,
                    f"Q: {question} A: {answer}",
                )
        self.logger.log(question, answer, timings=timings)
        first_token_label = (
            f"{timings['first_token_ms']}ms"
            if timings["first_token_ms"] is not None
            else "n/a"
        )
        self.overlay.show_status(
            self._idle_status(
                f"first {first_token_label} • total {total_seconds:.1f}s"
            )
        )

    def run(self):
        while True:
            item = self.work_queue.get()
            if item is None:
                return
            if isinstance(item, ManualQuestion):
                cancel_event = self._begin_operation()
                try:
                    self._take_current_filler()
                    if item.source == "manual":
                        self.overlay.clear_transcript()
                    self._answer_question(
                        item.text,
                        cancel_event=cancel_event,
                        source=item.source,
                        context_override=item.context_override,
                        response_style=item.response_style,
                    )
                except Exception:
                    traceback.print_exc()
                finally:
                    self._finish_operation(cancel_event)
                continue

            is_retry = isinstance(item, RetryTranscription)
            audio_work = item.audio if is_retry else item
            if not audio_work.is_final:
                self._start_partial(pcm_bytes_to_float32(audio_work.pcm_bytes))
                continue

            with self._last_audio_lock:
                self._last_audio_work = audio_work
            cancel_event = self._begin_operation()
            operation_started = time.perf_counter()
            try:
                self.overlay.show_status(
                    "Retrying transcription…" if is_retry else "Transcribing…"
                )
                filler = self._take_current_filler()
                transcription_started = time.perf_counter()
                transcription_options = {}
                if self.whisper_model != "base.en":
                    transcription_options["model_name"] = self.whisper_model
                if self.whisper_language != "en":
                    transcription_options["language"] = self.whisper_language
                result = transcribe_with_metadata(
                    pcm_bytes_to_float32(audio_work.pcm_bytes),
                    SAMPLE_RATE,
                    **transcription_options,
                )
                transcription_seconds = time.perf_counter() - transcription_started
                if cancel_event.is_set():
                    self.overlay.show_status(
                        self._idle_status("transcription cancelled")
                    )
                    continue
                self.overlay.show_transcript(
                    result.text,
                    result.confidence,
                    result.no_speech_probability,
                    result.is_reliable,
                )
                if not result.text.strip():
                    self.overlay.show_status(
                        self._idle_status("no clear speech detected")
                    )
                    continue
                if not result.is_reliable:
                    self.overlay.show_status("Review transcript • low confidence")
                    continue
                if not is_retry and self._is_duplicate_audio_question(
                    result.text,
                    audio_work.captured_at,
                ):
                    self.overlay.show_status(self._idle_status("duplicate ignored"))
                    continue

                self._answer_question(
                    result.text,
                    filler,
                    cancel_event=cancel_event,
                    operation_started=operation_started,
                    transcription_seconds=transcription_seconds,
                    source="audio_retry" if is_retry else "audio",
                )
            except Exception:
                traceback.print_exc()
                self.overlay.show_status(self._idle_status())
            finally:
                self._finish_operation(cancel_event)


class CaptureThread(threading.Thread):
    def __init__(
        self,
        work_queue: WorkQueue,
        pa: pyaudio.PyAudio,
        device_index: int,
        overlay: OverlayWindow,
        *,
        vad_aggressiveness: int = 3,
        silence_timeout_ms: int = 1000,
    ):
        super().__init__(daemon=True)
        self.work_queue = work_queue
        self.pa = pa
        self.device_index = device_index
        self.overlay = overlay
        self.vad_aggressiveness = vad_aggressiveness
        self.silence_timeout_ms = silence_timeout_ms
        # threading.Thread already owns a private _stop() method used by join().
        # Shadowing it with an Event makes a completed capture thread unjoinable.
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()

    def run(self):
        pa = self.pa
        stream = None
        try:
            stream = open_capture_stream(pa, self.device_index)
            segmenter = self._new_segmenter()
            was_paused = False
            while not self._stop_event.is_set():
                frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
                if self._pause_event.is_set():
                    if not was_paused:
                        segmenter = self._new_segmenter()
                        was_paused = True
                    continue
                if was_paused:
                    segmenter = self._new_segmenter()
                    was_paused = False
                utterance = segmenter.push_frame(frame)
                if utterance is not None:
                    pcm_bytes, is_final = utterance
                    self.work_queue.submit_audio(
                        AudioWork(pcm_bytes, is_final, time.monotonic())
                    )
        except Exception as exc:
            self.overlay.show_error(
                f"Audio capture stopped: {exc}. Reopen the app, select this input "
                "in Setup, and run Test Audio Capture. Also check macOS microphone "
                "permission."
            )
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            pa.terminate()

    def stop(self):
        self._stop_event.set()

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._pause_event.set()
        else:
            self._pause_event.clear()

    def _new_segmenter(self) -> UtteranceSegmenter:
        return UtteranceSegmenter(
            vad_aggressiveness=self.vad_aggressiveness,
            silence_trailing_ms=self.silence_timeout_ms,
        )


def main():
    app = QApplication(sys.argv)

    try:
        settings = load_settings()
        settings_error = None
    except SettingsError as exc:
        settings = AppSettings()
        settings_error = str(exc)

    try:
        pa = pyaudio.PyAudio()
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Audio initialization failed",
            "PyAudio could not initialize the system audio service.\n\n"
            f"Details: {exc}\n\n"
            "Restart the app and check macOS microphone permission. If the "
            "problem continues, reinstall the Python audio dependencies.",
        )
        return

    profiles = list_application_profiles()
    setup = SetupWindow(
        pa,
        settings,
        application_profiles=profiles,
        settings_load_error=settings_error,
    )
    if setup.exec() != QDialog.DialogCode.Accepted:
        pa.terminate()
        return
    settings = setup.settings
    device_index = settings.audio_device_index
    if device_index is None:
        pa.terminate()
        QMessageBox.critical(
            None,
            "Audio input missing",
            "No audio input was selected. Reopen the app and choose an input "
            "device in Setup.",
        )
        return

    _signal_timer = QTimer()
    _signal_timer.timeout.connect(lambda: None)
    _signal_timer.start(200)

    overlay = OverlayWindow(profiles, settings=settings)
    overlay.show()

    logger = SessionLogger(
        Path("sessions"),
        enabled=settings.session_logging_enabled,
    )
    work_queue = WorkQueue()

    worker = Worker(
        work_queue,
        overlay,
        logger,
        ollama_model=settings.ollama_model,
        ollama_base_url=settings.ollama_base_url,
        whisper_model=settings.whisper_model,
        whisper_language=settings.whisper_language,
        default_response_style=settings.answer_style,
    )
    worker.set_profile(overlay.selected_profile())
    overlay.manual_question_submitted.connect(worker.submit_manual_question)
    overlay.transcript_correction_submitted.connect(worker.submit_transcript_correction)
    overlay.retry_transcription_requested.connect(worker.retry_last_transcription)
    overlay.cancel_requested.connect(worker.cancel_current)
    overlay.profile_changed.connect(worker.set_profile)
    capture = CaptureThread(
        work_queue,
        pa,
        device_index,
        overlay,
        vad_aggressiveness=settings.vad_aggressiveness,
        silence_timeout_ms=settings.silence_timeout_ms,
    )
    overlay.listening_paused_changed.connect(capture.set_paused)
    overlay.listening_paused_changed.connect(worker.set_listening_paused)
    overlay.regenerate_requested.connect(worker.regenerate_last_answer)
    overlay.shorter_answer_requested.connect(
        lambda: worker.regenerate_last_answer("shorter")
    )
    overlay.more_detail_requested.connect(
        lambda: worker.regenerate_last_answer("more_detail")
    )
    startup_cancelled = threading.Event()
    shutdown_started = threading.Event()
    lifecycle_lock = threading.Lock()

    def initialize_services():
        try:
            overlay.show_status("Loading speech model…")
            try:
                preload_transcriber(settings.whisper_model)
            except Exception as exc:
                raise RuntimeError(
                    f"Whisper model '{settings.whisper_model}' could not load: "
                    f"{exc}. Check the model name and internet access for its "
                    "first download, then reopen Setup."
                ) from exc
            if startup_cancelled.is_set():
                return

            overlay.show_status("Loading language model…")
            try:
                preload_llm(
                    model=settings.ollama_model,
                    base_url=settings.ollama_base_url,
                    strict=True,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Ollama model '{settings.ollama_model}' could not start: "
                    f"{exc}. Make sure Ollama is running and the model is "
                    "installed, then reopen Setup."
                ) from exc
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
        overlay.stop_global_visibility_shortcut()
        app.quit()

    signal.signal(signal.SIGINT, handle_sigint)
    overlay.quit_requested.connect(handle_sigint)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
