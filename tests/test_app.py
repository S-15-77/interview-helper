import threading
from unittest.mock import Mock, patch

import numpy as np

from src.app import (
    AudioWork,
    CaptureThread,
    ManualQuestion,
    RetryTranscription,
    Worker,
    WorkQueue,
    main,
    normalize_question,
    pcm_bytes_to_float32,
    trim_context,
)
from src.settings import AppSettings
from src.transcriber import TranscriptionResult


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
        response_style="default",
    )
    logger.log.assert_called_once()
    log_args, log_kwargs = logger.log.call_args
    assert log_args == ("What is IR?", "Compiler IR answer")
    assert log_kwargs["timings"]["source"] == "manual"
    assert log_kwargs["timings"]["transcription_ms"] == 0
    assert log_kwargs["timings"]["first_token_ms"] is not None
    assert log_kwargs["timings"]["total_ms"] >= 0


def test_completed_coached_answer_arms_candidate_microphone_for_same_question():
    candidate_coach = Mock()
    worker = Worker(
        WorkQueue(),
        Mock(),
        Mock(),
        candidate_coach=candidate_coach,
    )
    worker.set_profile("compiler-role")
    candidate_coach.reset_mock()

    with patch("src.app.stream_answer", return_value=iter(["Practice answer"])):
        worker._answer_question("Tell me about a difficult project.")

    candidate_coach.arm_for_question.assert_called_once_with(
        "Tell me about a difficult project.",
        "compiler-role",
    )


def test_work_queue_is_bounded_and_replaces_stale_audio():
    work_queue = WorkQueue(maxsize=1)

    assert work_queue.submit_audio(AudioWork(b"partial-1", False, 1.0))
    assert work_queue.submit_audio(AudioWork(b"partial-2", False, 2.0))
    assert work_queue.submit_audio(AudioWork(b"final-1", True, 3.0))
    assert work_queue.submit_audio(AudioWork(b"final-2", True, 4.0))

    assert work_queue.qsize() == 1
    assert work_queue.get() == AudioWork(b"final-2", True, 4.0)


def test_pausing_discards_only_audio_work():
    work_queue = WorkQueue()
    work_queue.submit_audio(AudioWork(b"audio", True, 1.0))
    work_queue.discard_audio()

    assert work_queue.qsize() == 0

    work_queue.submit_manual(ManualQuestion("Keep this"))
    work_queue.discard_audio()

    assert work_queue.get() == ManualQuestion("Keep this")


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


def test_retry_transcription_replaces_queued_audio_as_priority_work():
    work_queue = WorkQueue()
    superseded = Mock()
    work_queue.set_supersede_callback(superseded)
    old_audio = AudioWork(b"old", True, 1.0)
    retry_audio = AudioWork(b"retry", True, 2.0)
    work_queue.submit_audio(old_audio)

    assert work_queue.submit_retry(RetryTranscription(retry_audio))
    assert not work_queue.submit_audio(AudioWork(b"later", True, 3.0))

    superseded.assert_called_once_with()
    assert work_queue.get() == RetryTranscription(retry_audio)


def test_question_normalization_ignores_case_spacing_and_punctuation():
    assert normalize_question("  What IS an IR?! ") == "what is an ir"


def test_simulate_mode_arms_candidate_without_generating_or_revealing_answer():
    overlay = Mock()
    logger = Mock()
    coach = Mock()
    worker = Worker(WorkQueue(), overlay, logger, candidate_coach=coach, practice_mode="simulate")

    with patch("src.app.stream_answer") as stream:
        worker._answer_question("Design a cache")

    overlay.begin_simulation.assert_called_once_with("Design a cache")
    coach.arm_for_question.assert_called_once_with("Design a cache", None)
    stream.assert_not_called()
    logger.log.assert_called_once()


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
        patch(
            "src.app.transcribe_with_metadata",
            return_value=TranscriptionResult("What is IR?", 0.9, 0.05),
        ),
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
    overlay.show_transcript.assert_called_once_with("What is IR?", 0.9, 0.05, True)
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
        patch(
            "src.app.transcribe_with_metadata",
            return_value=TranscriptionResult("What is IR?", 0.9, 0.05),
        ),
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


def test_low_confidence_transcript_is_shown_but_not_answered():
    work_queue = WorkQueue()
    overlay = Mock()
    logger = Mock()
    worker = Worker(work_queue, overlay, logger)
    confidence_review_shown = threading.Event()

    def observe_status(message):
        if message == "Review transcript • low confidence":
            confidence_review_shown.set()

    overlay.show_status.side_effect = observe_status
    result = TranscriptionResult("Was that hash map?", 0.12, 0.8)

    with (
        patch("src.app.transcribe_with_metadata", return_value=result),
        patch("src.app.stream_answer") as stream,
    ):
        worker.start()
        work_queue.submit_audio(AudioWork(b"\x00\x00", True, 10.0))
        assert confidence_review_shown.wait(timeout=1)
        worker.stop()
        worker.join(timeout=1)

    overlay.show_transcript.assert_called_once_with(
        "Was that hash map?",
        0.12,
        0.8,
        False,
    )
    stream.assert_not_called()
    logger.log.assert_not_called()


def test_corrected_transcript_cancels_old_work_and_generates_answer():
    work_queue = WorkQueue()
    overlay = Mock()
    logger = Mock()
    worker = Worker(work_queue, overlay, logger)
    corrected_logged = threading.Event()
    logger.log.side_effect = lambda *_args, **_kwargs: corrected_logged.set()

    with patch("src.app.stream_answer", return_value=iter(["Corrected answer"])):
        worker.start()
        worker.submit_transcript_correction("  What is a hash map?  ")
        assert corrected_logged.wait(timeout=1)
        worker.stop()
        worker.join(timeout=1)

    overlay.begin_question.assert_called_once_with("What is a hash map?")
    assert logger.log.call_args.kwargs["timings"]["source"] == "correction"


def test_retry_transcription_reuses_audio_and_bypasses_duplicate_filter():
    work_queue = WorkQueue()
    overlay = Mock()
    logger = Mock()
    worker = Worker(work_queue, overlay, logger)
    review_shown = threading.Event()
    retry_logged = threading.Event()
    results = [
        TranscriptionResult("What is IR?", 0.1, 0.8),
        TranscriptionResult("What is IR?", 0.9, 0.05),
    ]

    def observe_status(message):
        if message == "Review transcript • low confidence":
            review_shown.set()

    overlay.show_status.side_effect = observe_status
    logger.log.side_effect = lambda *_args, **_kwargs: retry_logged.set()

    with (
        patch("src.app.transcribe_with_metadata", side_effect=results) as transcribe,
        patch("src.app.stream_answer", return_value=iter(["An IR is..."])),
    ):
        worker.start()
        work_queue.submit_audio(AudioWork(b"\x00\x00", True, 10.0))
        assert review_shown.wait(timeout=1)
        worker.retry_last_transcription()
        assert retry_logged.wait(timeout=1)
        worker.stop()
        worker.join(timeout=1)

    assert transcribe.call_count == 2
    assert logger.log.call_args.kwargs["timings"]["source"] == "audio_retry"


def test_retry_without_captured_audio_reports_that_nothing_is_available():
    overlay = Mock()
    worker = Worker(WorkQueue(), overlay, Mock())

    worker.retry_last_transcription()

    overlay.show_status.assert_called_once_with("Listening • no transcript to retry")


def test_pause_state_discards_audio_and_changes_idle_status():
    work_queue = WorkQueue()
    overlay = Mock()
    worker = Worker(work_queue, overlay, Mock())
    work_queue.submit_audio(AudioWork(b"queued", True, 1.0))

    worker.set_listening_paused(True)

    assert work_queue.qsize() == 0
    overlay.show_status.assert_called_with("Paused…")

    worker.set_listening_paused(False)

    overlay.show_status.assert_called_with("Listening…")


def test_pausing_does_not_hide_an_active_generation_status():
    overlay = Mock()
    worker = Worker(WorkQueue(), overlay, Mock())
    operation = worker._begin_operation()

    worker.set_listening_paused(True)

    overlay.show_status.assert_not_called()
    worker._finish_operation(operation)


def test_regenerate_reuses_original_context_instead_of_previous_answer():
    work_queue = WorkQueue()
    worker = Worker(work_queue, Mock(), Mock())
    worker.context = "Earlier interview context"

    with patch("src.app.stream_answer", return_value=iter(["First answer"])):
        worker._answer_question("What is IR?")

    assert "First answer" in worker.context

    worker.regenerate_last_answer("shorter")
    queued = work_queue.get()

    assert queued == ManualQuestion(
        "What is IR?",
        source="shorter",
        context_override="Earlier interview context",
        response_style="shorter",
    )


def test_regenerate_without_previous_answer_reports_status():
    overlay = Mock()
    worker = Worker(WorkQueue(), overlay, Mock())

    worker.regenerate_last_answer()

    overlay.show_status.assert_called_once_with("Listening • no answer to regenerate")


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
    assert [call.args[0] for call in logger.log.call_args_list] == ["Typed priority question"]
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


def test_capture_pause_state_can_be_toggled_before_start():
    capture = CaptureThread(WorkQueue(), Mock(), 1, Mock())

    capture.set_paused(True)
    assert capture._pause_event.is_set()

    capture.set_paused(False)
    assert not capture._pause_event.is_set()


def test_worker_passes_configured_models_language_endpoint_and_style():
    worker = Worker(
        WorkQueue(),
        Mock(),
        Mock(),
        ollama_model="llama3.2:latest",
        ollama_base_url="http://127.0.0.1:11434",
        whisper_model="small.en",
        whisper_language="auto",
        default_response_style="shorter",
    )

    with patch("src.app.stream_answer", return_value=iter(["Short answer"])) as stream:
        worker._answer_question("Explain IR")

    stream.assert_called_once_with(
        "Explain IR",
        "",
        model="llama3.2:latest",
        profile_name=None,
        response_style="shorter",
        base_url="http://127.0.0.1:11434",
    )

    # The live run loop is covered separately; configuration on final audio is
    # asserted through the partial path here without starting a long-lived thread.
    with (
        patch("src.app.transcribe", return_value="partial") as transcribe_partial,
        patch("src.llm_client.generate_filler", return_value="Thinking"),
    ):
        worker._process_partial(np.zeros(10, dtype=np.float32), 0)
    transcribe_partial.assert_called_once()
    args, kwargs = transcribe_partial.call_args
    assert np.array_equal(args[0], np.zeros(10, dtype=np.float32))
    assert args[1] == 16000
    assert kwargs == {"model_name": "small.en", "language": "auto"}


def test_capture_uses_configured_vad_and_silence_timeout():
    capture = CaptureThread(
        WorkQueue(),
        Mock(),
        1,
        Mock(),
        vad_aggressiveness=1,
        silence_timeout_ms=1700,
    )

    with patch("src.app.UtteranceSegmenter") as segmenter:
        capture._new_segmenter()

    segmenter.assert_called_once_with(
        vad_aggressiveness=1,
        silence_trailing_ms=1700,
    )


def test_startup_opens_setup_before_runtime_and_cancel_exits_cleanly():
    pa = Mock()
    application = Mock()
    setup = Mock()
    setup.exec.return_value = 0

    with (
        patch("src.app.QApplication", return_value=application),
        patch("src.app.pyaudio.PyAudio", return_value=pa),
        patch("src.app.load_settings", return_value=AppSettings()),
        patch("src.app.list_application_profiles", return_value=["compiler-role"]),
        patch("src.app.SetupWindow", return_value=setup) as setup_window,
        patch("src.app.OverlayWindow") as overlay,
    ):
        main()

    setup_window.assert_called_once()
    assert setup_window.call_args.kwargs["application_profiles"] == ["compiler-role"]
    pa.terminate.assert_called_once_with()
    overlay.assert_not_called()
