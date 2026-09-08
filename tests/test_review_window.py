import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from src.interview_plan import QuestionBank
from src.review_window import ReviewWindow
from src.session_repository import SessionRepository

_app = QApplication.instance() or QApplication([])


def test_review_dashboard_lists_session_filters_and_attempt_details(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "20260908-100000.jsonl").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "type": "candidate_attempt",
                "timestamp": "2026-09-08T10:00:00",
                "question": "Design a cache",
                "profile": "platform-role",
                "category": "system_design",
                "difficulty": "advanced",
                "attempt_number": 1,
                "candidate_transcript": "I would use an LRU policy.",
                "metrics": {"duration_seconds": 20, "words_per_minute": 120, "filler_counts": {}},
                "feedback": {
                    "question_type": "technical",
                    "scores": {"relevance": 4},
                    "improvements": ["Explain eviction trade-offs."],
                    "improved_answer": "Use an LRU cache with a bounded capacity.",
                },
            }
        )
        + "\n"
    )
    window = ReviewWindow(
        SessionRepository(sessions),
        question_bank=QuestionBank(tmp_path / "question-bank.json"),
    )

    assert window.session_list.count() == 1
    assert window.attempt_list.count() == 1
    assert "LRU policy" in window.detail.toPlainText()
    window.category_filter.setCurrentIndex(window.category_filter.findData("behavioral"))
    assert window.attempt_list.count() == 0
    window.close()
