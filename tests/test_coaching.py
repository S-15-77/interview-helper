import json
from unittest.mock import Mock, patch

from src.coaching import (
    AttemptTracker,
    CoachingFeedback,
    PRACTICE_FRAMEWORK,
    analyze_candidate_response,
    analyze_speech_metrics,
    build_coaching_prompt,
    fallback_feedback,
    parse_coaching_response,
)


def feedback(scores=None, **overrides):
    values = {
        "question_type": "behavioral",
        "scores": scores
        or {
            "relevance": 3,
            "star_completeness": 3,
            "clarity_structure": 3,
            "conciseness": 3,
            "technical_correctness": None,
            "profile_support": 3,
        },
        "facts": ("The answer included a result.",),
        "unsupported_claims": (),
        "missing_tradeoffs": (),
        "improvements": ("Clarify the action.",),
        "improved_answer": "Grounded improved answer.",
    }
    values.update(overrides)
    return CoachingFeedback(**values)


def test_speech_metrics_measure_pace_fillers_and_repeated_phrases():
    transcript = (
        "Um, I built the service and I built the service. You know, "
        "I built the service and reduced latency."
    )

    metrics = analyze_speech_metrics(transcript, duration_seconds=10)

    assert metrics.word_count == 19
    assert metrics.words_per_minute == 114
    assert dict(metrics.filler_counts) == {"um": 1, "you know": 1}
    assert "i built the" in metrics.repeated_phrases


def test_coaching_prompt_requires_grounding_and_separates_facts_from_suggestions():
    metrics = analyze_speech_metrics("I reduced latency by 30 percent.", 8)

    prompt = build_coaching_prompt(
        "Tell me about a technical challenge.",
        "I reduced latency by 30 percent.",
        "Profile: latency project, 30 percent reduction.",
        metrics,
    )

    assert "Never invent candidate experience" in prompt
    assert "only allowed sources" in prompt
    assert "facts: direct, neutral observations" in prompt
    assert "at most two specific coaching suggestions" in prompt
    assert "unsupported by the supplied profile" in prompt
    assert "technical_correctness" in prompt
    assert "missing_tradeoffs" in prompt


def test_coaching_json_is_parsed_and_improvements_are_limited_to_two():
    raw = json.dumps(
        {
            "question_type": "technical",
            "scores": {
                "relevance": 5,
                "star_completeness": None,
                "clarity_structure": 4,
                "conciseness": 4,
                "technical_correctness": 8,
                "profile_support": 3,
            },
            "facts": ["The response named a hash map."],
            "unsupported_claims": ["Scale claim is absent from the profile."],
            "missing_tradeoffs": ["Memory versus lookup speed."],
            "improvements": ["One", "Two", "Three"],
            "improved_answer": "A grounded answer.",
        }
    )

    result = parse_coaching_response(raw)

    assert result.scores["technical_correctness"] == 5
    assert result.scores["star_completeness"] is None
    assert result.improvements == ("One", "Two")
    assert result.missing_tradeoffs == ("Memory versus lookup speed.",)


def test_failed_model_analysis_still_returns_actionable_local_feedback():
    metrics = analyze_speech_metrics("Um, I helped with the project.", 12)

    result = fallback_feedback(
        "Tell me about a time you led a project.",
        "Um, I helped with the project.",
        metrics,
        "Ollama unavailable",
    )

    assert result.source == "local_fallback"
    assert 1 <= result.scores["relevance"] <= 5
    assert 1 <= len(result.improvements) <= 2
    assert result.improved_answer == PRACTICE_FRAMEWORK
    assert "Ollama unavailable" in result.facts[-1]


def test_behavioral_improvement_uses_framework_when_profile_and_details_are_missing():
    response = Mock()
    response.json.return_value = {
        "response": json.dumps(
            {
                "question_type": "behavioral",
                "scores": {
                    "relevance": 2,
                    "star_completeness": 1,
                    "clarity_structure": 2,
                    "conciseness": 4,
                    "technical_correctness": None,
                    "profile_support": 1,
                },
                "facts": [],
                "unsupported_claims": [],
                "missing_tradeoffs": [],
                "improvements": ["Add detail."],
                "improved_answer": "I invented a detailed project.",
            }
        )
    }
    metrics = analyze_speech_metrics("I worked on something difficult.", 5)

    with patch("src.coaching.requests.post", return_value=response):
        result = analyze_candidate_response(
            "Tell me about a time you faced a challenge.",
            "I worked on something difficult.",
            "",
            metrics,
            model="qwen:latest",
            base_url="http://localhost:11434",
        )

    assert result.improved_answer == PRACTICE_FRAMEWORK
    assert "no application profile" in result.unsupported_claims[-1].lower()


def test_ollama_connection_failure_automatically_uses_local_feedback():
    from requests import ConnectionError

    metrics = analyze_speech_metrics("I would use a hash map.", 5)
    with patch(
        "src.coaching.requests.post",
        side_effect=ConnectionError("connection refused"),
    ):
        result = analyze_candidate_response(
            "How would you implement a lookup?",
            "I would use a hash map.",
            "",
            metrics,
            model="qwen:latest",
            base_url="http://localhost:11434",
        )

    assert result.source == "local_fallback"
    assert result.improvements
    assert "connection refused" in result.facts[-1]


def test_attempt_tracker_compares_repeated_answers_to_same_question():
    tracker = AttemptTracker()
    first_metrics = analyze_speech_metrics("Um, I built a service.", 10)
    second_metrics = analyze_speech_metrics("I built a service and reduced latency.", 10)
    first_scores = feedback().scores
    second_scores = {**first_scores, "relevance": 4, "clarity_structure": 4}
    tracker.add(
        question="Tell me about a project.",
        transcript="Um, I built a service.",
        transcription_confidence=0.8,
        metrics=first_metrics,
        feedback=feedback(),
    )

    second = tracker.add(
        question="tell me about a project!",
        transcript="I built a service and reduced latency.",
        transcription_confidence=0.9,
        metrics=second_metrics,
        feedback=feedback(scores=second_scores),
    )

    assert second.attempt_number == 2
    assert second.comparison is not None
    assert second.comparison.score_deltas["relevance"] == 1
    assert second.comparison.filler_delta == -1
    assert "Overall scores improved" in second.comparison.summary
    assert "relevance +1" in second.comparison.summary
