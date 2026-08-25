import queue
import threading
from unittest.mock import Mock, patch

import numpy as np

from src.app import (
    CaptureThread,
    ManualQuestion,
    Worker,
    pcm_bytes_to_float32,
    trim_context,
)


def test_pcm_bytes_to_float32_scales_int16_range():
    ints = np.array([0, 32767, -32768], dtype="<i2")
    floats = pcm_bytes_to_float32(ints.tobytes())

    assert floats.dtype == np.float32
    assert np.allclose(floats, [0.0, 32767 / 32768.0, -1.0])


def test_trim_context_keeps_last_n_words():
    context = " ".join(f"word{i}" for i in range(190))
    new_text = " ".join(f"new{i}" for i in range(20))

    trimmed = trim_context(context, new_text, word_limit=200)

    words = trimmed.split()
    assert len(words) == 200
    assert words[-1] == "new19"


def test_trim_context_handles_empty_context():
    trimmed = trim_context("", "hello world", word_limit=200)
    assert trimmed == "hello world"


def test_final_utterance_invalidates_in_flight_partial():
    worker = Worker(queue.Queue(), Mock(), Mock())
    transcription_started = threading.Event()
    finish_transcription = threading.Event()

    def delayed_transcription(*_args):
        transcription_started.set()
        assert finish_transcription.wait(timeout=1)
        return "Tell me about yourself"

    with (
        patch("src.app.transcribe", side_effect=delayed_transcription),
        patch("src.llm_client.generate_filler", return_value="Let me think for a moment."),
    ):
        worker._start_partial(np.zeros(100, dtype=np.float32))
        partial_thread = worker._partial_thread
        assert partial_thread is not None
        assert transcription_started.wait(timeout=1)
        assert worker._take_current_filler() == ""
        finish_transcription.set()
        partial_thread.join(timeout=1)

    assert worker.current_filler == ""


def test_final_utterance_takes_completed_filler_once():
    worker = Worker(queue.Queue(), Mock(), Mock())
    worker.current_filler = "Let me think for a moment."

    assert worker._take_current_filler() == "Let me think for a moment."
    assert worker._take_current_filler() == ""


def test_manual_question_is_added_to_worker_queue():
    work_queue = queue.Queue()
    worker = Worker(work_queue, Mock(), Mock())

    worker.submit_manual_question("  What is IR?  ")

    assert work_queue.get_nowait() == ManualQuestion("What is IR?")


def test_switching_application_profile_clears_conversation_context():
    worker = Worker(queue.Queue(), Mock(), Mock())
    worker.context = "previous ML discussion"

    worker.set_profile("compiler-role")

    assert worker._prompt_state() == ("", "compiler-role")


def test_answer_uses_selected_application_profile():
    overlay = Mock()
    logger = Mock()
    worker = Worker(queue.Queue(), overlay, logger)
    worker.set_profile("compiler-role")

    with patch("src.app.stream_answer", return_value=iter(["Compiler IR answer"])) as stream:
        worker._answer_question("What is IR?")

    stream.assert_called_once_with(
        "What is IR?",
        "",
        profile_name="compiler-role",
    )
    logger.log.assert_called_once_with("What is IR?", "Compiler IR answer")


def test_stopped_capture_thread_can_be_joined():
    audio_stream = Mock()
    pa = Mock()
    capture = CaptureThread(queue.Queue(), pa, 1, Mock())

    with patch("src.app.open_capture_stream", return_value=audio_stream):
        capture.stop()
        capture.start()
        capture.join(timeout=1)

    assert not capture.is_alive()
    audio_stream.stop_stream.assert_called_once()
    audio_stream.close.assert_called_once()
    pa.terminate.assert_called_once()
