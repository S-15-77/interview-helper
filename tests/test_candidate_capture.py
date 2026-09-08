from unittest.mock import Mock, patch

import numpy as np

from src.candidate_capture import (
    CandidateAudioWork,
    CandidateCaptureThread,
    CandidateResponseWorker,
    CandidateWorkQueue,
)
from src.coaching import CoachingFeedback
from src.transcriber import TranscriptionResult


def test_candidate_queue_preserves_every_completed_response_in_order():
    queue = CandidateWorkQueue()
    first = CandidateAudioWork("Q1", None, b"one", 1.0, 1.0)
    second = CandidateAudioWork("Q2", None, b"two", 2.0, 2.0)

    queue.submit(first)
    queue.submit(second)

    assert queue.get() == first
    assert queue.get() == second


def test_candidate_capture_arms_for_question_and_detects_finished_answer():
    class FakeSegmenter:
        def __init__(self, **_kwargs):
            self.calls = 0
            self.is_speaking = False

        def push_frame(self, _frame):
            self.calls += 1
            self.is_speaking = True
            if self.calls == 2:
                return (b"\x01\x00" * 4800, True)
            return None

    stream = Mock()
    stream.read.return_value = b"\x01\x00" * 480
    pa = Mock()
    overlay = Mock()
    queue = CandidateWorkQueue()
    capture = CandidateCaptureThread(queue, pa, 4, overlay)
    capture.arm("Tell me about a project", "compiler-role")

    with (
        patch("src.candidate_capture.open_capture_stream", return_value=stream),
        patch("src.candidate_capture.UtteranceSegmenter", FakeSegmenter),
    ):
        capture.start()
        work = queue.get()
        capture.stop()
        capture.join(timeout=1)

    assert work.question == "Tell me about a project"
    assert work.profile_name == "compiler-role"
    assert work.duration_seconds == 0.3
    states = [call.args[0] for call in overlay.show_candidate_state.call_args_list]
    assert "Candidate mic: speaking…" in states
    assert "Candidate response captured • transcribing…" in states
    stream.stop_stream.assert_called_once_with()
    stream.close.assert_called_once_with()
    pa.terminate.assert_called_once_with()


def test_candidate_worker_transcribes_analyzes_logs_and_displays_attempt():
    queue = CandidateWorkQueue()
    capture = Mock()
    overlay = Mock()
    logger = Mock()
    logger.save_candidate_audio.return_value = None
    worker = CandidateResponseWorker(
        queue,
        capture,
        overlay,
        logger,
        whisper_model="small.en",
        whisper_language="auto",
        ollama_model="qwen:latest",
        ollama_base_url="http://localhost:11434",
    )
    work = CandidateAudioWork(
        "What is a hash map?",
        "backend-role",
        np.full(16000, 1000, dtype="<i2").tobytes(),
        1.0,
        1.0,
    )
    model_feedback = CoachingFeedback(
        question_type="technical",
        scores={
            "relevance": 4,
            "star_completeness": None,
            "clarity_structure": 4,
            "conciseness": 4,
            "technical_correctness": 4,
            "profile_support": 5,
        },
        facts=("The answer defined lookup behavior.",),
        unsupported_claims=(),
        missing_tradeoffs=("Discuss collision handling.",),
        improvements=("Name collision handling.",),
        improved_answer="A hash map stores key-value pairs.",
    )

    with (
        patch(
            "src.candidate_capture.transcribe_with_metadata",
            return_value=TranscriptionResult("A hash map stores values.", 0.9, 0.02),
        ) as transcribe,
        patch("src.candidate_capture.load_knowledge_base", return_value="Resume facts"),
        patch(
            "src.candidate_capture.analyze_candidate_response",
            return_value=model_feedback,
        ) as analyze,
    ):
        worker._process(work)

    assert transcribe.call_args.kwargs == {
        "model_name": "small.en",
        "language": "auto",
    }
    analyze.assert_called_once()
    attempt = logger.log_candidate_attempt.call_args.args[0]
    assert attempt.transcript == "A hash map stores values."
    assert attempt.attempt_number == 1
    overlay.show_candidate_attempt.assert_called_once_with(attempt)
    overlay.show_candidate_transcript.assert_called_once_with(
        "A hash map stores values.", 0.9, 0.02
    )


def test_retry_rearms_the_same_question_and_profile():
    capture = Mock()
    worker = CandidateResponseWorker(
        CandidateWorkQueue(),
        capture,
        Mock(),
        Mock(),
        whisper_model="base.en",
        whisper_language="en",
        ollama_model="qwen:latest",
        ollama_base_url="http://localhost:11434",
    )
    worker.arm_for_question("Tell me about a conflict", "role")

    worker.retry_last()

    assert capture.arm.call_args_list[-1].args == (
        "Tell me about a conflict",
        "role",
    )


def test_pause_disarms_candidate_microphone_and_resume_rearms_last_question():
    capture = Mock()
    overlay = Mock()
    worker = CandidateResponseWorker(
        CandidateWorkQueue(),
        capture,
        overlay,
        Mock(),
        whisper_model="base.en",
        whisper_language="en",
        ollama_model="qwen:latest",
        ollama_base_url="http://localhost:11434",
    )
    worker.arm_for_question("Question", "role")

    worker.set_paused(True)
    worker.retry_last()
    worker.set_paused(False)

    capture.disarm.assert_called_once_with()
    assert capture.arm.call_args_list[-1].args == ("Question", "role")
    assert "paused" in overlay.show_candidate_state.call_args_list[-2].args[0]


def test_transcription_failure_still_produces_actionable_attempt():
    capture = Mock()
    overlay = Mock()
    logger = Mock()
    logger.save_candidate_audio.return_value = None
    worker = CandidateResponseWorker(
        CandidateWorkQueue(),
        capture,
        overlay,
        logger,
        whisper_model="missing-model",
        whisper_language="en",
        ollama_model="qwen:latest",
        ollama_base_url="http://localhost:11434",
    )
    work = CandidateAudioWork("Explain IR", None, b"\x00\x00" * 4800, 0.3, 1.0)

    with patch(
        "src.candidate_capture.transcribe_with_metadata",
        side_effect=RuntimeError("Whisper unavailable"),
    ):
        worker._process(work)

    attempt = overlay.show_candidate_attempt.call_args.args[0]
    assert attempt.feedback.source == "local_fallback"
    assert attempt.feedback.improvements
    assert "Whisper unavailable" in attempt.feedback.facts[-1]
    logger.log_candidate_attempt.assert_called_once_with(attempt)
