from src.llm_client import build_prompt


def test_build_prompt_includes_question_and_star_guidance():
    prompt = build_prompt(context="", question="Tell me about a time you failed.")
    assert "Tell me about a time you failed." in prompt
    assert "STAR" in prompt


def test_build_prompt_includes_context_block_when_present():
    prompt = build_prompt(
        context="Interviewer: let's talk about teamwork.",
        question="Give an example.",
    )
    assert "Recent conversation:" in prompt
    assert "Interviewer: let's talk about teamwork." in prompt
    assert "Give an example." in prompt


def test_build_prompt_omits_context_block_when_context_empty():
    prompt = build_prompt(context="", question="What is a hash map?")
    assert "Recent conversation:" not in prompt
