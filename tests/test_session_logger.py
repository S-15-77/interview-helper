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


def test_read_all_returns_empty_list_when_no_entries_logged():
    with tempfile.TemporaryDirectory() as tmp:
        logger = SessionLogger(Path(tmp), start_time=datetime(2026, 7, 27, 10, 0, 0))
        assert logger.read_all() == []
