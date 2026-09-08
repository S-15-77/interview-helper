import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.llm_client import (
    build_prompt,
    generate_filler,
    list_application_profiles,
    load_knowledge_base,
    load_skills,
    preload,
    stream_answer,
)


def test_build_prompt_includes_question_and_star_guidance():
    prompt = build_prompt(context="", question="Tell me about a time you failed.")
    assert "Tell me about a time you failed." in prompt
    assert "STAR" in prompt


def test_prompt_limits_product_to_consensual_mock_interview_practice():
    prompt = build_prompt(context="", question="Tell me about yourself.")

    assert "only for practice with a consenting friend" in prompt
    assert "never for use during a real employer interview" in prompt
    assert "actual or mock interview" not in prompt


def test_prompt_describes_the_audio_source_accurately():
    prompt = build_prompt(context="", question="What is a hash map?")

    assert "friend's voice is captured from the call's system audio" in prompt
    assert "selected input device" in prompt
    assert "BlackHole for call system audio" in prompt
    assert "separate candidate microphone" in prompt
    assert "explicit session consent" in prompt
    assert "kept logically separate" in prompt


def test_prompt_forbids_fabricated_personal_experience():
    prompt = build_prompt(context="", question="Tell me about a conflict at work.")

    assert "Do NOT invent personal facts" in prompt
    assert "Every personal claim must be supported by the Application Profile" in prompt
    assert "Never present a generic or plausible scenario" in prompt
    assert "standard, believable placeholder scenario" not in prompt


def test_prompt_requires_a_clearly_marked_framework_when_evidence_is_missing():
    prompt = build_prompt(context="", question="Tell me about a conflict at work.")

    assert "PRACTICE FRAMEWORK — NOT READY TO SPEAK" in prompt
    assert "Situation: [real context]" in prompt
    assert "Task: [your real responsibility]" in prompt
    assert "Action: [specific actions you personally took]" in prompt
    assert "Result: [real, supportable outcome]" in prompt
    assert "Add this completed story to star_stories.md" in prompt


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


def test_build_prompt_adds_shorter_answer_adjustment():
    prompt = build_prompt(
        context="",
        question="Explain a hash map.",
        response_style="shorter",
    )

    assert "substantially shorter" in prompt
    assert "stay under 90 words" in prompt


def test_build_prompt_adds_more_detail_adjustment():
    prompt = build_prompt(
        context="",
        question="Explain a hash map.",
        response_style="more_detail",
    )

    assert "make this version more detailed" in prompt
    assert "within the core 200-word limit" in prompt


def test_build_prompt_rejects_unknown_response_style():
    with pytest.raises(ValueError):
        build_prompt("", "Question", response_style="unbounded")


def test_default_knowledge_base_excludes_readme_and_saved_applications(tmp_path):
    my_data = tmp_path / "my_data"
    application = my_data / "applications" / "compiler-role"
    application.mkdir(parents=True)
    (my_data / "README.md").write_text("documentation only")
    (my_data / "profile.md").write_text("legacy candidate profile")
    (application / "resume.md").write_text("compiler resume")

    knowledge = load_knowledge_base(my_data_dir=my_data)

    assert "legacy candidate profile" in knowledge
    assert "documentation only" not in knowledge
    assert "compiler resume" not in knowledge


def test_skills_loader_excludes_its_readme(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "README.md").write_text("documentation only")
    (skills / "compiler.md").write_text("compiler-specific instructions")
    monkeypatch.chdir(tmp_path)

    loaded = load_skills()

    assert "compiler-specific instructions" in loaded
    assert "documentation only" not in loaded


def test_selected_application_loads_only_its_files(tmp_path):
    my_data = tmp_path / "my_data"
    compiler = my_data / "applications" / "compiler-role"
    ml = my_data / "applications" / "ml-role"
    compiler.mkdir(parents=True)
    ml.mkdir(parents=True)
    (my_data / "profile.md").write_text("default resume")
    (compiler / "resume.md").write_text("compiler resume")
    (compiler / "job_description.md").write_text("build compiler passes")
    (compiler / "README.md").write_text("compiler documentation")
    (ml / "resume.md").write_text("machine learning resume")

    knowledge = load_knowledge_base("compiler-role", my_data_dir=my_data)

    assert "compiler resume" in knowledge
    assert "build compiler passes" in knowledge
    assert "compiler documentation" not in knowledge
    assert "machine learning resume" not in knowledge
    assert "default resume" not in knowledge


def test_application_profiles_are_listed_in_sorted_order(tmp_path):
    applications = tmp_path / "applications"
    for name in ("zeta-role", "alpha-role"):
        profile = applications / name
        profile.mkdir(parents=True)
        (profile / "resume.md").write_text(name)
    empty_profile = applications / "empty-role"
    empty_profile.mkdir()

    assert list_application_profiles(applications) == ["alpha-role", "zeta-role"]


def test_application_profile_rejects_path_traversal(tmp_path):
    my_data = tmp_path / "my_data"
    (my_data / "applications").mkdir(parents=True)

    with pytest.raises(ValueError):
        load_knowledge_base("..", my_data_dir=my_data)


def test_build_prompt_labels_active_application_profile():
    with (
        patch(
            "src.llm_client.load_knowledge_base",
            return_value="compiler resume and JD",
        ),
        patch("src.llm_client.load_skills", return_value=""),
    ):
        prompt = build_prompt("", "What is IR?", profile_name="compiler-role")

    assert "Active Application Profile (compiler-role):" in prompt
    assert "compiler resume and JD" in prompt
    assert "intermediate representation" in prompt


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


def test_shorter_answer_uses_smaller_generation_cap():
    done_line = json.dumps({"response": "", "done": True}).encode()
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.iter_lines.return_value = [done_line]

    with patch("src.llm_client.requests.post", return_value=mock_response) as post:
        list(stream_answer("What is a hash map?", response_style="shorter"))

    payload = post.call_args.kwargs["json"]
    assert payload["options"]["num_predict"] == 180
    assert "stay under 90 words" in payload["prompt"]


def test_stream_answer_uses_configured_ollama_endpoint_and_model():
    done_line = json.dumps({"response": "", "done": True}).encode()
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.iter_lines.return_value = [done_line]

    with patch("src.llm_client.requests.post", return_value=mock_response) as post:
        list(
            stream_answer(
                "What is IR?",
                model="llama3.2:latest",
                base_url="http://127.0.0.1:11434/",
            )
        )

    assert post.call_args.args[0] == "http://127.0.0.1:11434/api/generate"
    assert post.call_args.kwargs["json"]["model"] == "llama3.2:latest"


def test_strict_preload_surfaces_ollama_startup_failure():
    from requests import ConnectionError

    with patch(
        "src.llm_client.requests.post",
        side_effect=ConnectionError("connection refused"),
    ):
        with pytest.raises(ConnectionError, match="connection refused"):
            preload(strict=True)
