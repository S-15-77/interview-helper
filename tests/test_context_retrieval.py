from src.context_retrieval import ContextRetriever, ConversationState, classify_question


def test_question_classifier_covers_practice_rounds():
    assert classify_question("Tell me about a time you disagreed") == "behavioral"
    assert classify_question("Design a scalable URL shortener") == "system_design"
    assert classify_question("Code an algorithm for duplicate values") == "coding"
    assert classify_question("Why this company?") == "recruiter"
    assert classify_question("Explain database indexes") == "technical"


def test_retriever_selects_relevant_passages_respects_budget_and_detects_edits(tmp_path):
    profile = tmp_path / "profile"
    skills = tmp_path / "skills"
    profile.mkdir()
    skills.mkdir()
    resume = profile / "resume.md"
    resume.write_text("Python compiler optimization and LLVM passes.\n\nUnrelated sales work.")
    (skills / "hr_playbook.md").write_text("Behavioral STAR advice")
    (skills / "technical.md").write_text("Explain technical trade-offs")
    retriever = ContextRetriever(profile, skills, word_budget=10)

    selected, details = retriever.retrieve("Explain LLVM compiler passes")
    assert "LLVM" in selected
    assert details["question_type"] == "technical"
    assert details["selected_words"] <= 10

    resume.write_text("Rust compiler optimization and MIR passes.")
    changed, _ = retriever.retrieve("Explain Rust MIR passes")
    assert "Rust" in changed


def test_structured_conversation_state_tracks_topics_stories_and_turn_limit():
    state = ConversationState(max_turns=2)
    state.add_turn("Tell me about a conflict", "Resolved it", story="cache decision")
    state.add_turn("Explain a hash map", "Key value storage")
    state.add_turn("Design a service", "Distributed architecture")

    rendered = state.render()
    assert "behavioral" in rendered
    assert "cache decision" in rendered
    assert "Tell me about a conflict" not in rendered
    assert "Explain a hash map" in rendered
