import json
from datetime import datetime

from src.session_repository import (
    SESSION_SCHEMA_VERSION,
    SessionRepository,
    redact_personal_identifiers,
)


def test_repository_migrates_legacy_entries_and_summarizes_attempts(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    path = sessions / "20260908-100000.jsonl"
    path.write_text(
        json.dumps({"timestamp": "2026-09-08T10:00:00", "question": "Q", "answer": "A"})
        + "\n"
        + json.dumps(
            {
                "schema_version": 2,
                "type": "candidate_attempt",
                "timestamp": "2026-09-08T10:01:00",
                "question": "Tell me about a time",
                "category": "behavioral",
                "attempt_number": 1,
                "metrics": {
                    "duration_seconds": 60,
                    "words_per_minute": 120,
                    "filler_counts": {"um": 2},
                },
                "feedback": {
                    "question_type": "behavioral",
                    "scores": {"relevance": 4, "star_completeness": 2},
                },
            }
        )
        + "\n"
    )
    repository = SessionRepository(sessions)

    entries = repository.read(path)
    assert entries[0]["schema_version"] == SESSION_SCHEMA_VERSION
    assert entries[0]["type"] == "generated_answer"
    metrics = repository.metrics(entries)
    assert metrics["average_duration_seconds"] == 60
    assert metrics["filler_words_per_minute"] == 2
    assert metrics["underdeveloped_star_prompts"] == ["Tell me about a time"]
    assert repository.list_sessions()[0].attempts == 1


def test_export_redacts_identifiers_and_metadata_round_trips(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    source = sessions / "session.jsonl"
    source.write_text(
        json.dumps(
            {
                "question": "Contact?",
                "answer": "me@example.com +1 416 555 1212",
                "timestamp": "2026-01-01",
            }
        )
        + "\n"
    )
    repository = SessionRepository(sessions)
    repository.update_question("Contact?", note="practice again", marked=True)
    output = repository.export_markdown(source, tmp_path / "export.md", redact=True)

    assert "me@example.com" not in output.read_text()
    assert "[REDACTED EMAIL]" in output.read_text()
    assert repository.metadata()["questions"]["contact"]["marked"] is True


def test_cleanup_removes_expired_session_and_audio(tmp_path):
    sessions = tmp_path / "sessions"
    audio = sessions / "audio" / "old"
    audio.mkdir(parents=True)
    path = sessions / "old.jsonl"
    path.write_text("{}\n")
    old = datetime(2020, 1, 1).timestamp()
    import os

    os.utime(path, (old, old))
    repository = SessionRepository(sessions)
    deleted = repository.cleanup(30, now=datetime(2026, 1, 1))
    assert deleted == [path]
    assert not audio.exists()


def test_personal_identifier_redaction_handles_profile_links():
    redacted = redact_personal_identifiers("a@b.com https://linkedin.com/in/person")
    assert "[REDACTED EMAIL]" in redacted
    assert "[REDACTED PROFILE]" in redacted
