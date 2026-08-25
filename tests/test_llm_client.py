import json
from unittest.mock import MagicMock, Mock, patch

from src.llm_client import build_prompt, generate_filler, stream_answer


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


def test_generate_filler_strips_quotes_from_response():
    mock_response = Mock()
    mock_response.json.return_value = {"response": '"Let me think about that for a second..."'}

    with patch("src.llm_client.requests.post", return_value=mock_response):
        filler = generate_filler("tell me about a time you")

    assert filler == "Let me think about that for a second..."


def test_generate_filler_falls_back_on_request_error():
    with patch("src.llm_client.requests.post", side_effect=Exception("boom")):
        filler = generate_filler("tell me about a time you")

    assert filler == "That's a great question, let me think..."


def test_stream_answer_yields_chunks_and_stops_at_done():
    lines = [
        json.dumps({"response": "Hello"}).encode(),
        json.dumps({"response": " world"}).encode(),
        json.dumps({"response": "", "done": True}).encode(),
    ]
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.iter_lines.return_value = lines

    with patch("src.llm_client.requests.post", return_value=mock_response):
        chunks = list(stream_answer("What is a hash map?"))

    assert chunks == ["Hello", " world"]
    mock_response.raise_for_status.assert_called_once()


def test_stream_answer_caps_generated_tokens():
    done_line = json.dumps({"response": "", "done": True}).encode()
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.iter_lines.return_value = [done_line]

    with patch("src.llm_client.requests.post", return_value=mock_response) as post:
        list(stream_answer("What is a hash map?"))

    assert post.call_args.kwargs["json"]["options"]["num_predict"] == 320
