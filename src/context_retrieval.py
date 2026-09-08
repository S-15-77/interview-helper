"""Small, deterministic context retriever for local interview prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

QUESTION_TYPES = ("recruiter", "behavioral", "technical", "coding", "system_design")
_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}")
_STOP = {
    "about",
    "and",
    "are",
    "could",
    "describe",
    "for",
    "from",
    "have",
    "how",
    "that",
    "the",
    "this",
    "tell",
    "what",
    "when",
    "where",
    "with",
    "would",
    "your",
}


def classify_question(question: str) -> str:
    text = question.casefold()
    if re.search(r"\b(system design|design (?:a|an|the)|architecture|scalab|distributed)\b", text):
        return "system_design"
    if re.search(
        r"\b(code|coding|algorithm|complexity|array|linked list|tree|graph|leetcode)\b", text
    ):
        return "coding"
    if re.search(
        r"\b(tell me about a time|describe a (?:time|situation)|conflict|failure|mistake|"
        r"leadership|teamwork|disagree|challenge)\b",
        text,
    ):
        return "behavioral"
    if re.search(
        r"\b(why (?:this|our)|salary|availability|relocat|visa|strength|weakness|yourself)\b", text
    ):
        return "recruiter"
    return "technical"


def keywords(text: str) -> set[str]:
    return {
        word.casefold()
        for word in _WORD.findall(text)
        if len(word) > 2 and word.casefold() not in _STOP
    }


def _chunks(text: str, max_words: int = 180) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    result: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        for start in range(0, len(words), max_words):
            result.append(" ".join(words[start : start + max_words]))
    return result


@dataclass
class ConversationState:
    """Structured state replaces an unlabelled rolling tail of conversation text."""

    turns: list[tuple[str, str]] = field(default_factory=list)
    topics_discussed: list[str] = field(default_factory=list)
    stories_used: list[str] = field(default_factory=list)
    open_follow_ups: list[str] = field(default_factory=list)
    max_turns: int = 6

    def add_turn(self, question: str, answer: str, story: str | None = None) -> None:
        self.turns.append((question.strip(), answer.strip()))
        del self.turns[: -self.max_turns]
        topic = classify_question(question)
        if topic not in self.topics_discussed:
            self.topics_discussed.append(topic)
        if story and story not in self.stories_used:
            self.stories_used.append(story)
        self.open_follow_ups = _detect_follow_ups(answer)

    def clear(self) -> None:
        self.turns.clear()
        self.topics_discussed.clear()
        self.stories_used.clear()
        self.open_follow_ups.clear()

    def render(self, word_budget: int = 260) -> str:
        sections: list[str] = []
        if self.topics_discussed:
            sections.append("Topics discussed: " + ", ".join(self.topics_discussed))
        if self.stories_used:
            sections.append("STAR stories already used: " + ", ".join(self.stories_used))
        if self.open_follow_ups:
            sections.append("Open follow-ups: " + "; ".join(self.open_follow_ups))
        sections.extend(f"Q: {question}\nA: {answer}" for question, answer in self.turns)
        words = "\n".join(sections).split()
        return " ".join(words[-word_budget:])


def _detect_follow_ups(answer: str) -> list[str]:
    # Explicit TODO-like markers are useful during generated interview plans and
    # avoid trying to infer private facts from arbitrary prose.
    return [
        item.strip() for item in re.findall(r"(?:follow[- ]?up|next):\s*([^.!?]+)", answer, re.I)
    ][:3]


class ContextRetriever:
    """Caches source files by mtime and ranks small passages for a question."""

    def __init__(self, profile_root: Path, skills_root: Path, *, word_budget: int = 900):
        self.profile_root = Path(profile_root)
        self.skills_root = Path(skills_root)
        self.word_budget = word_budget
        self._cache: dict[Path, tuple[int, int, str]] = {}

    def _read(self, path: Path) -> str:
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(path)
        if cached and cached[:2] == signature:
            return cached[2]
        text = path.read_text(encoding="utf-8")
        self._cache[path] = (*signature, text)
        return text

    @staticmethod
    def _documents(root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        return sorted(
            path
            for path in root.glob("**/*")
            if path.is_file()
            and path.suffix.lower() in {".md", ".txt"}
            and path.name.casefold() != "readme.md"
        )

    def _relevant_skills(self, question_type: str) -> list[Path]:
        docs = self._documents(self.skills_root)
        hints = {
            "recruiter": ("hr", "recruit", "communication"),
            "behavioral": ("hr", "behavior", "star", "communication"),
            "technical": ("technical",),
            "coding": ("coding", "algorithm", "technical"),
            "system_design": ("system", "design", "technical"),
        }[question_type]
        selected = [path for path in docs if any(hint in path.stem.casefold() for hint in hints)]
        return selected or docs[:1]

    def retrieve(self, question: str) -> tuple[str, dict[str, object]]:
        question_type = classify_question(question)
        query = keywords(question)
        candidates: list[tuple[float, str, str]] = []
        for source_kind, paths in (
            ("skill", self._relevant_skills(question_type)),
            ("profile", self._documents(self.profile_root)),
        ):
            for path in paths:
                filename_words = keywords(path.stem.replace("_", " "))
                for index, chunk in enumerate(_chunks(self._read(path))):
                    overlap = len(query & keywords(chunk))
                    boost = 2 if query & filename_words else 0
                    # Job descriptions and resumes remain useful even with sparse overlap.
                    base = 0.25 if path.stem in {"resume", "job_description"} else 0
                    candidates.append(
                        (overlap + boost + base, f"{source_kind}:{path.name}:{index}", chunk)
                    )
        candidates.sort(key=lambda item: (-item[0], item[1]))
        selected: list[tuple[str, str]] = []
        used = 0
        for score, label, chunk in candidates:
            if score <= 0 and selected:
                continue
            chunk_words = chunk.split()
            remaining = self.word_budget - used
            if remaining <= 0:
                break
            selected.append((label, " ".join(chunk_words[:remaining])))
            used += min(len(chunk_words), remaining)
        text = "\n\n".join(f"--- {label} ---\n{chunk}" for label, chunk in selected)
        inspection = {
            "question_type": question_type,
            "word_budget": self.word_budget,
            "selected_sources": [label for label, _ in selected],
            "selected_words": used,
        }
        return text, inspection
