from datetime import datetime
from pathlib import Path
import tempfile

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
