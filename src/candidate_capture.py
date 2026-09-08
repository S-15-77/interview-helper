import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, replace

import numpy as np

from src.audio_capture import FRAME_SIZE, SAMPLE_RATE, UtteranceSegmenter, open_capture_stream
from src.coaching import (
    AttemptTracker,
    CoachingFeedback,
    analyze_candidate_response,
    analyze_speech_metrics,
    fallback_feedback,
)
from src.llm_client import load_knowledge_base
from src.transcriber import TranscriptionResult, transcribe_with_metadata


@dataclass(frozen=True)
class CandidateAudioWork:
    question: str
    profile_name: str | None
    pcm_bytes: bytes
    duration_seconds: float
    captured_at: float


class CandidateWorkQueue:
    """FIFO queue that preserves every completed candidate response."""

    def __init__(self):
        self._items: deque[CandidateAudioWork] = deque()
        self._condition = threading.Condition()
        self._stopped = False

    def submit(self, work: CandidateAudioWork) -> bool:
        with self._condition:
            if self._stopped:
                return False
            self._items.append(work)
            self._condition.notify()
            return True

    def get(self) -> CandidateAudioWork | None:
        with self._condition:
            while not self._items and not self._stopped:
                self._condition.wait()
            if self._stopped:
                return None
            return self._items.popleft()

    def stop(self) -> None:
        with self._condition:
            self._stopped = True
            self._items.clear()
            self._condition.notify_all()


class CandidateCaptureThread(threading.Thread):
    def __init__(
        self,
        work_queue: CandidateWorkQueue,
        pa,
        device_index: int,
        overlay,
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
        self._stop_event = threading.Event()
        self._armed = threading.Event()
        self._assignment_lock = threading.Lock()
        self._assignment: tuple[str, str | None, int] | None = None
        self._generation = 0

    def arm(self, question: str, profile_name: str | None = None) -> None:
        with self._assignment_lock:
            self._generation += 1
            self._assignment = (question, profile_name, self._generation)
            self._armed.set()
        self.overlay.show_candidate_state(
            "Candidate mic: listening — answer when ready."
        )

    def disarm(self) -> None:
        with self._assignment_lock:
            self._generation += 1
            self._assignment = None
            self._armed.clear()
        self.overlay.show_candidate_state("Candidate mic: waiting for a question.")

    def _current_assignment(self) -> tuple[str, str | None, int] | None:
        with self._assignment_lock:
            return self._assignment

    def _new_segmenter(self) -> UtteranceSegmenter:
        return UtteranceSegmenter(
            vad_aggressiveness=self.vad_aggressiveness,
            partial_ms=60_000,
            silence_trailing_ms=self.silence_timeout_ms,
        )

    def run(self) -> None:
        stream = None
        segmenter = self._new_segmenter()
        active_generation: int | None = None
        speaking = False
        speech_started_at: float | None = None
        try:
            stream = open_capture_stream(self.pa, self.device_index)
            self.overlay.show_candidate_state(
                "Candidate mic: ready — waiting for a question."
            )
            while not self._stop_event.is_set():
                frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
                assignment = self._current_assignment()
                if assignment is None or not self._armed.is_set():
                    if active_generation is not None:
                        segmenter = self._new_segmenter()
                        active_generation = None
                        speaking = False
                        speech_started_at = None
                    continue
                question, profile_name, generation = assignment
                if generation != active_generation:
                    segmenter = self._new_segmenter()
                    active_generation = generation
                    speaking = False
                    speech_started_at = None
                utterance = segmenter.push_frame(frame)
                if segmenter.is_speaking and not speaking:
                    speaking = True
                    speech_started_at = time.monotonic()
                    self.overlay.show_candidate_state("Candidate mic: speaking…")
                elif not segmenter.is_speaking and speaking and utterance is None:
                    # The segmenter can discard a very short noise burst instead
                    # of returning an utterance. Return to listening rather than
                    # leaving the UI stuck in a speaking state.
                    speaking = False
                    speech_started_at = None
                    self.overlay.show_candidate_state(
                        "Candidate mic: listening — answer when ready."
                    )
                if utterance is None:
                    continue
                pcm_bytes, is_final = utterance
                if not is_final:
                    continue
                with self._assignment_lock:
                    still_current = (
                        self._assignment is not None
                        and self._assignment[2] == generation
                    )
                    if still_current:
                        self._assignment = None
                        self._armed.clear()
                if not still_current:
                    continue
                voiced_duration = len(pcm_bytes) / (2 * SAMPLE_RATE)
                elapsed_duration = (
                    max(
                        0.0,
                        time.monotonic()
                        - speech_started_at
                        - self.silence_timeout_ms / 1000,
                    )
                    if speech_started_at is not None
                    else 0.0
                )
                duration = max(voiced_duration, elapsed_duration)
                self.work_queue.submit(
                    CandidateAudioWork(
                        question=question,
                        profile_name=profile_name,
                        pcm_bytes=pcm_bytes,
                        duration_seconds=duration,
                        captured_at=time.monotonic(),
                    )
                )
                self.overlay.show_candidate_state(
                    "Candidate response captured • transcribing…"
                )
                segmenter = self._new_segmenter()
                active_generation = None
                speaking = False
                speech_started_at = None
        except Exception as exc:
            self.overlay.show_candidate_state(
                f"Candidate microphone stopped: {exc}. Reopen Setup and test the "
                "candidate microphone and macOS permission."
            )
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            self.pa.terminate()

    def stop(self) -> None:
        self._stop_event.set()
        self._armed.clear()


class CandidateResponseWorker(threading.Thread):
    def __init__(
        self,
        work_queue: CandidateWorkQueue,
        capture: CandidateCaptureThread,
        overlay,
        logger,
        *,
        whisper_model: str,
        whisper_language: str,
        ollama_model: str,
        ollama_base_url: str,
    ):
        super().__init__(daemon=True)
        self.work_queue = work_queue
        self.capture = capture
        self.overlay = overlay
        self.logger = logger
        self.whisper_model = whisper_model
        self.whisper_language = whisper_language
        self.ollama_model = ollama_model
        self.ollama_base_url = ollama_base_url
        self.tracker = AttemptTracker()
        self._last_assignment_lock = threading.Lock()
        self._last_assignment: tuple[str, str | None] | None = None
        self._paused = threading.Event()

    def arm_for_question(self, question: str, profile_name: str | None) -> None:
        with self._last_assignment_lock:
            self._last_assignment = (question, profile_name)
        if self._paused.is_set():
            self.overlay.show_candidate_state("Candidate mic: paused.")
        else:
            self.capture.arm(question, profile_name)

    def cancel_listening(self) -> None:
        self.capture.disarm()

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._paused.set()
            self.capture.disarm()
            self.overlay.show_candidate_state("Candidate mic: paused.")
            return
        self._paused.clear()
        with self._last_assignment_lock:
            assignment = self._last_assignment
        if assignment is not None:
            self.capture.arm(*assignment)
        else:
            self.overlay.show_candidate_state(
                "Candidate mic: ready — waiting for a question."
            )

    def retry_last(self) -> None:
        with self._last_assignment_lock:
            assignment = self._last_assignment
        if assignment is None:
            self.overlay.show_candidate_state(
                "Candidate mic: no question is available to retry."
            )
            return
        if self._paused.is_set():
            self.overlay.show_candidate_state(
                "Candidate mic: paused — resume listening before trying again."
            )
            return
        self.capture.arm(*assignment)

    def stop(self) -> None:
        self.capture.stop()
        self.work_queue.stop()

    def run(self) -> None:
        while True:
            work = self.work_queue.get()
            if work is None:
                return
            try:
                self._process(work)
            except Exception:
                traceback.print_exc()
                self.overlay.show_candidate_state(
                    "Candidate coaching failed unexpectedly. Try the answer again."
                )

    def _process(self, work: CandidateAudioWork) -> None:
        audio = np.frombuffer(work.pcm_bytes, dtype="<i2").astype(np.float32)
        audio /= 32768.0
        transcription_error = None
        try:
            result = transcribe_with_metadata(
                audio,
                SAMPLE_RATE,
                model_name=self.whisper_model,
                language=self.whisper_language,
            )
        except Exception as exc:
            transcription_error = str(exc)
            result = TranscriptionResult("", 0.0, 1.0)
        self.overlay.show_candidate_transcript(
            result.text,
            result.confidence,
            result.no_speech_probability,
        )
        metrics = analyze_speech_metrics(result.text, work.duration_seconds)
        audio_error = None
        try:
            audio_path = self.logger.save_candidate_audio(
                work.pcm_bytes,
                SAMPLE_RATE,
            )
        except Exception as exc:
            audio_path = None
            audio_error = str(exc)
        self.overlay.show_candidate_state("Analyzing candidate response…")
        if result.text.strip():
            try:
                profile_data = load_knowledge_base(work.profile_name)
                profile_error = None
            except Exception as exc:
                profile_data = ""
                profile_error = str(exc)
            try:
                feedback = analyze_candidate_response(
                    work.question,
                    result.text,
                    profile_data,
                    metrics,
                    model=self.ollama_model,
                    base_url=self.ollama_base_url,
                )
            except Exception as exc:
                feedback = fallback_feedback(
                    work.question,
                    result.text,
                    metrics,
                    f"Model coaching failed: {exc}",
                )
            extra_facts: list[str] = []
            if not result.is_reliable:
                extra_facts.append(
                    "The transcript confidence was low; verify the detected response before relying on detailed feedback."
                )
            if profile_error:
                extra_facts.append(
                    "The application profile could not be loaded: " + profile_error
                )
            if audio_error:
                extra_facts.append(
                    "Candidate audio could not be retained: " + audio_error
                )
            if extra_facts:
                feedback = replace(
                    feedback,
                    facts=feedback.facts + tuple(extra_facts),
                )
        else:
            feedback = fallback_feedback(
                work.question,
                "",
                metrics,
                (
                    "Candidate transcription failed: " + transcription_error
                    if transcription_error
                    else "No clear candidate speech was transcribed. Check the microphone and retry."
                ),
            )
            if audio_error:
                feedback = replace(
                    feedback,
                    facts=feedback.facts
                    + ("Candidate audio could not be retained: " + audio_error,),
                )
        attempt = self.tracker.add(
            question=work.question,
            transcript=result.text,
            transcription_confidence=result.confidence,
            metrics=metrics,
            feedback=feedback,
            audio_path=audio_path,
        )
        self.overlay.show_candidate_attempt(attempt)
        try:
            self.logger.log_candidate_attempt(attempt)
        except Exception as exc:
            self.overlay.show_candidate_state(
                f"Candidate coaching ready • attempt {attempt.attempt_number} • "
                f"session log failed: {exc}"
            )
        else:
            self.overlay.show_candidate_state(
                f"Candidate coaching ready • attempt {attempt.attempt_number}."
            )
