from datetime import datetime
from pathlib import Path
import tempfile
from types import SimpleNamespace
import wave

from src.session_logger import SessionLogger


def test_log_round_trips_entry():
    with tempfile.TemporaryDirectory() as tmp:
        logger = SessionLogger(Path(tmp), start_time=datetime(2026, 7, 27, 10, 0, 0))
        logger.log(
            "What is a hash map?",
            "A hash map is...",
            timestamp=datetime(2026, 7, 27, 10, 0, 5),
        )

        entries = logger.read_all()

        assert len(entries) == 1
        assert entries[0]["question"] == "What is a hash map?"
        assert entries[0]["answer"] == "A hash map is..."
        assert entries[0]["timestamp"] == "2026-07-27T10:00:05"


def test_log_appends_multiple_entries_in_order():
    with tempfile.TemporaryDirectory() as tmp:
        logger = SessionLogger(Path(tmp), start_time=datetime(2026, 7, 27, 10, 0, 0))
        logger.log("Q1", "A1")
        logger.log("Q2", "A2")

        entries = logger.read_all()

        assert [e["question"] for e in entries] == ["Q1", "Q2"]


def test_log_preserves_pipeline_timings():
    with tempfile.TemporaryDirectory() as tmp:
        logger = SessionLogger(Path(tmp))
        timings = {
            "source": "audio",
            "transcription_ms": 420,
            "first_token_ms": 180,
            "generation_ms": 1300,
            "total_ms": 1720,
        }

        logger.log("Q", "A", timings=timings)

        assert logger.read_all()[0]["timings"] == timings


def test_read_all_returns_empty_list_when_no_entries_logged():
    with tempfile.TemporaryDirectory() as tmp:
        logger = SessionLogger(Path(tmp), start_time=datetime(2026, 7, 27, 10, 0, 0))
        assert logger.read_all() == []


def test_disabled_logging_does_not_create_a_directory_or_file(tmp_path):
    sessions = tmp_path / "sessions"
    logger = SessionLogger(sessions, enabled=False)

    logger.log("Private question", "Private answer")

    assert not sessions.exists()
    assert logger.read_all() == []


def test_candidate_attempt_is_logged_as_structured_feedback(tmp_path):
    logger = SessionLogger(
        tmp_path,
        start_time=datetime(2026, 7, 27, 10, 0, 0),
    )
    attempt = SimpleNamespace(
        question="Tell me about a project",
        transcript="I built a service.",
        attempt_number=1,
        transcription_confidence=0.91,
        audio_path=None,
        metrics=SimpleNamespace(
            duration_seconds=12.0,
            word_count=5,
            words_per_minute=25,
            filler_counts=(("um", 1),),
            repeated_phrases=(),
        ),
        feedback=SimpleNamespace(
            question_type="behavioral",
            scores={"relevance": 4},
            facts=("The response named a service.",),
            unsupported_claims=(),
            missing_tradeoffs=(),
            improvements=("Add a result.",),
            improved_answer="Grounded example.",
            source="ollama",
        ),
        comparison=None,
    )

    logger.log_candidate_attempt(attempt)
    entry = logger.read_all()[0]

    assert entry["type"] == "candidate_attempt"
    assert entry["candidate_transcript"] == "I built a service."
    assert entry["feedback"]["improvements"] == ["Add a result."]
    assert entry["metrics"]["filler_counts"] == {"um": 1}


def test_candidate_audio_retention_is_optional_and_writes_valid_wav(tmp_path):
    transcript_only = SessionLogger(tmp_path / "transcript", audio_enabled=False)
    assert transcript_only.save_candidate_audio(b"\x01\x00" * 160, 16000) is None
    assert not transcript_only.audio_dir.exists()

    retained = SessionLogger(
        tmp_path / "retained",
        start_time=datetime(2026, 7, 27, 10, 0, 0),
        enabled=False,
        audio_enabled=True,
    )
    path = retained.save_candidate_audio(b"\x01\x00" * 160, 16000)

    assert path is not None
    with wave.open(path, "rb") as audio_file:
        assert audio_file.getnchannels() == 1
        assert audio_file.getsampwidth() == 2
        assert audio_file.getframerate() == 16000
        assert audio_file.getnframes() == 160
