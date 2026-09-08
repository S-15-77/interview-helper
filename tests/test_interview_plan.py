import json
from unittest.mock import Mock, patch

from src.interview_plan import (
    InterviewQuestion,
    QuestionBank,
    generate_follow_up,
    generate_interview_plan,
)


def test_interview_plan_parses_model_output_and_fills_to_requested_length(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "job_description.md").write_text("Build Python services")
    response = Mock()
    response.json.return_value = {
        "response": json.dumps(
            [
                {
                    "text": "Explain Python concurrency.",
                    "category": "technical",
                    "difficulty": "ignored",
                    "topic": "Python",
                }
            ]
        )
    }
    with patch("src.interview_plan.requests.post", return_value=response):
        questions = generate_interview_plan(
            profile,
            tmp_path / "skills",
            length=3,
            difficulty="advanced",
            rounds=("technical", "behavioral"),
            model="local",
            base_url="http://localhost:11434",
        )

    assert len(questions) == 3
    assert questions[0].difficulty == "advanced"
    assert len({question.text.casefold() for question in questions}) == 3


def test_follow_up_rejects_duplicate_question():
    response = Mock()
    response.json.return_value = {"response": "Why did you choose that?"}
    with patch("src.interview_plan.requests.post", return_value=response):
        assert (
            generate_follow_up(
                "Original?",
                "I chose it.",
                used_questions={"Why did you choose that?"},
                model="local",
                base_url="http://localhost:11434",
            )
            is None
        )


def test_question_bank_can_add_update_and_delete(tmp_path):
    bank = QuestionBank(tmp_path / "bank.json")
    identifier = bank.add(InterviewQuestion("Design a cache", "system_design", "advanced", "cache"))
    assert bank.load()[0]["status"] == "new"
    bank.update(identifier, status="mastered", topic="storage")
    assert bank.load()[0]["topic"] == "storage"
    bank.delete(identifier)
    assert bank.load() == []
