import threading
from unittest.mock import Mock, patch

import numpy as np

from src.app import (
    AudioWork,
    CaptureThread,
    ManualQuestion,
    Worker,
    WorkQueue,
    normalize_question,
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
    worker = Worker(WorkQueue(), Mock(), Mock())
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
    worker = Worker(WorkQueue(), Mock(), Mock())
    worker.current_filler = "Let me think for a moment."

    assert worker._take_current_filler() == "Let me think for a moment."
    assert worker._take_current_filler() == ""


def test_manual_question_is_added_to_worker_queue():
    work_queue = WorkQueue()
    worker = Worker(work_queue, Mock(), Mock())

    worker.submit_manual_question("  What is IR?  ")

    assert work_queue.get() == ManualQuestion("What is IR?")


def test_switching_application_profile_clears_conversation_context():
    worker = Worker(WorkQueue(), Mock(), Mock())
    worker.context = "previous ML discussion"

    worker.set_profile("compiler-role")

    assert worker._prompt_state() == ("", "compiler-role")


def test_answer_uses_selected_application_profile():
    overlay = Mock()
    logger = Mock()
    worker = Worker(WorkQueue(), overlay, logger)
    worker.set_profile("compiler-role")

    with patch("src.app.stream_answer", return_value=iter(["Compiler IR answer"])) as stream:
        worker._answer_question("What is IR?")

    stream.assert_called_once_with(
        "What is IR?",
        "",
        profile_name="compiler-role",
    )
    logger.log.assert_called_once()
    log_args, log_kwargs = logger.log.call_args
    assert log_args == ("What is IR?", "Compiler IR answer")
    assert log_kwargs["timings"]["source"] == "manual"
    assert log_kwargs["timings"]["transcription_ms"] == 0
    assert log_kwargs["timings"]["first_token_ms"] is not None
    assert log_kwargs["timings"]["total_ms"] >= 0


def test_work_queue_is_bounded_and_replaces_stale_audio():
    work_queue = WorkQueue(maxsize=1)

    assert work_queue.submit_audio(AudioWork(b"partial-1", False, 1.0))
    assert work_queue.submit_audio(AudioWork(b"partial-2", False, 2.0))
    assert work_queue.submit_audio(AudioWork(b"final-1", True, 3.0))
    assert work_queue.submit_audio(AudioWork(b"final-2", True, 4.0))

    assert work_queue.qsize() == 1
    assert work_queue.get() == AudioWork(b"final-2", True, 4.0)


def test_manual_question_replaces_audio_and_supersedes_active_work():
    work_queue = WorkQueue(maxsize=3)
    superseded = Mock()
    work_queue.set_supersede_callback(superseded)
    work_queue.submit_audio(AudioWork(b"old audio", True, 1.0))

    assert work_queue.submit_manual(ManualQuestion("Typed question"))
    assert not work_queue.submit_audio(AudioWork(b"later audio", True, 2.0))

    superseded.assert_called_once_with()
    assert work_queue.qsize() == 1
    assert work_queue.get() == ManualQuestion("Typed question")


def test_question_normalization_ignores_case_spacing_and_punctuation():
    assert normalize_question("  What IS an IR?! ") == "what is an ir"


def test_duplicate_audio_question_is_detected_only_inside_window():
    worker = Worker(WorkQueue(), Mock(), Mock())

    assert not worker._is_duplicate_audio_question("What is IR?", 10.0)
    assert worker._is_duplicate_audio_question("what is ir", 20.0)
    assert not worker._is_duplicate_audio_question("What is IR?", 41.0)


def test_audio_pipeline_reports_states_and_logs_all_timings():
    work_queue = WorkQueue()
    overlay = Mock()
    logger = Mock()
    worker = Worker(work_queue, overlay, logger)
    answer_logged = threading.Event()
    logger.log.side_effect = lambda *_args, **_kwargs: answer_logged.set()

    with (
        patch("src.app.transcribe", return_value="What is IR?"),
        patch("src.app.stream_answer", return_value=iter(["An IR is..."])),
    ):
        worker.start()
        work_queue.submit_audio(AudioWork(b"\x00\x00", True, 10.0))
        assert answer_logged.wait(timeout=1)
        worker.stop()
        worker.join(timeout=1)

    statuses = [call.args[0] for call in overlay.show_status.call_args_list]
    assert "Transcribing…" in statuses
    assert "Generating…" in statuses
    assert statuses[-1].startswith("Listening • first ")
    timings = logger.log.call_args.kwargs["timings"]
    assert timings["source"] == "audio"
    assert timings["transcription_ms"] >= 0
    assert timings["first_token_ms"] >= 0
    assert timings["generation_ms"] >= 0
    assert timings["total_ms"] >= timings["generation_ms"]


def test_duplicate_audio_transcription_does_not_generate_another_answer():
    work_queue = WorkQueue()
    overlay = Mock()
    logger = Mock()
    worker = Worker(work_queue, overlay, logger)
    first_logged = threading.Event()
    duplicate_ignored = threading.Event()
    logger.log.side_effect = lambda *_args, **_kwargs: first_logged.set()

    def observe_status(message):
        if message == "Listening • duplicate ignored":
            duplicate_ignored.set()

    overlay.show_status.side_effect = observe_status

    with (
        patch("src.app.transcribe", return_value="What is IR?"),
        patch("src.app.stream_answer", return_value=iter(["An IR is..."])) as stream,
    ):
        worker.start()
        work_queue.submit_audio(AudioWork(b"\x00\x00", True, 10.0))
        assert first_logged.wait(timeout=1)
        work_queue.submit_audio(AudioWork(b"\x00\x00", True, 15.0))
        assert duplicate_ignored.wait(timeout=1)
        worker.stop()
        worker.join(timeout=1)

    stream.assert_called_once()
    logger.log.assert_called_once()


def test_manual_question_cancels_active_answer_and_runs_next():
    work_queue = WorkQueue()
    overlay = Mock()
    logger = Mock()
    worker = Worker(work_queue, overlay, logger)
    old_stream_started = threading.Event()
    release_old_stream = threading.Event()
    new_answer_logged = threading.Event()

    def answers(question, *_args, **_kwargs):
        if question == "Old audio question":
            def old_answer():
                old_stream_started.set()
                yield "old chunk"
                assert release_old_stream.wait(timeout=1)
                yield " stale chunk"

            return old_answer()
        return iter(["new answer"])

    def record_answer(question, *_args, **_kwargs):
        if question == "Typed priority question":
            new_answer_logged.set()

    logger.log.side_effect = record_answer

    with patch("src.app.stream_answer", side_effect=answers):
        worker.start()
        work_queue.submit_manual(ManualQuestion("Old audio question"))
        assert old_stream_started.wait(timeout=1)

        worker.submit_manual_question("Typed priority question")
        release_old_stream.set()

        assert new_answer_logged.wait(timeout=1)
        worker.stop()
        worker.join(timeout=1)

    assert not worker.is_alive()
    assert [call.args[0] for call in logger.log.call_args_list] == [
        "Typed priority question"
    ]
    overlay.show_cancelled.assert_called_once_with()


def test_cancel_current_stops_generation_and_clears_queued_work():
    work_queue = WorkQueue()
    overlay = Mock()
    logger = Mock()
    worker = Worker(work_queue, overlay, logger)
    stream_started = threading.Event()
    release_stream = threading.Event()

    def slow_answer(*_args, **_kwargs):
        stream_started.set()
        yield "first"
        assert release_stream.wait(timeout=1)
        yield "second"

    with patch("src.app.stream_answer", return_value=slow_answer()):
        worker.start()
        work_queue.submit_manual(ManualQuestion("Cancel this"))
        assert stream_started.wait(timeout=1)
        work_queue.submit_audio(AudioWork(b"queued", True, 2.0))

        worker.cancel_current()
        release_stream.set()
        worker.stop()
        worker.join(timeout=1)

    assert work_queue.qsize() == 0
    logger.log.assert_not_called()
    overlay.show_cancelled.assert_called_once_with()


def test_stopped_capture_thread_can_be_joined():
    audio_stream = Mock()
    pa = Mock()
    capture = CaptureThread(WorkQueue(), pa, 1, Mock())

    with patch("src.app.open_capture_stream", return_value=audio_stream):
        capture.stop()
        capture.start()
        capture.join(timeout=1)

    assert not capture.is_alive()
    audio_stream.stop_stream.assert_called_once()
    audio_stream.close.assert_called_once()
    pa.terminate.assert_called_once()
