"""Versioned local session storage, review metrics, privacy controls and exports."""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import cast

SESSION_SCHEMA_VERSION = 2
REVIEW_METADATA_VERSION = 1


def migrate_entry(entry: dict) -> dict:
    """Return a current-schema copy while preserving readable legacy JSONL."""
    migrated = dict(entry)
    version = migrated.get("schema_version", 1)
    if version == 1:
        migrated.setdefault("type", "generated_answer")
        migrated.setdefault("profile", None)
        migrated.setdefault("category", None)
        migrated.setdefault("difficulty", None)
        migrated["schema_version"] = SESSION_SCHEMA_VERSION
    elif version != SESSION_SCHEMA_VERSION:
        raise ValueError(f"Unsupported session schema version: {version}")
    return migrated


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    path: Path
    started_at: str
    profile: str | None
    questions: int
    attempts: int
    average_score: float | None


class SessionRepository:
    def __init__(self, sessions_dir: Path = Path("sessions")):
        self.sessions_dir = Path(sessions_dir)
        self.metadata_path = self.sessions_dir / "review_metadata.json"

    def paths(self) -> list[Path]:
        if not self.sessions_dir.is_dir():
            return []
        return sorted(self.sessions_dir.glob("*.jsonl"), reverse=True)

    def read(self, session: str | Path) -> list[dict]:
        path = self._resolve(session)
        if not path.exists():
            return []
        entries: list[dict] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    entries.append(migrate_entry(value))
            except (json.JSONDecodeError, ValueError) as exc:
                entries.append(
                    {
                        "schema_version": SESSION_SCHEMA_VERSION,
                        "type": "read_error",
                        "error": f"Line {line_number}: {exc}",
                    }
                )
        return entries

    def list_sessions(self) -> list[SessionSummary]:
        summaries: list[SessionSummary] = []
        for path in self.paths():
            entries = self.read(path)
            dated = [str(item.get("timestamp", "")) for item in entries if item.get("timestamp")]
            profiles = [item.get("profile") for item in entries if item.get("profile")]
            attempts = [item for item in entries if item.get("type") == "candidate_attempt"]
            generated = [item for item in entries if item.get("type") == "generated_answer"]
            scores = [
                score
                for item in attempts
                for score in item.get("feedback", {}).get("scores", {}).values()
                if isinstance(score, (int, float)) and not isinstance(score, bool)
            ]
            summaries.append(
                SessionSummary(
                    session_id=path.stem,
                    path=path,
                    started_at=min(dated) if dated else path.stem,
                    profile=profiles[0] if profiles else None,
                    questions=len(
                        {
                            item.get("question")
                            for item in generated + attempts
                            if item.get("question")
                        }
                    ),
                    attempts=len(attempts),
                    average_score=round(mean(scores), 2) if scores else None,
                )
            )
        return summaries

    def metrics(self, entries: list[dict]) -> dict[str, object]:
        attempts = [item for item in entries if item.get("type") == "candidate_attempt"]
        durations = [item.get("metrics", {}).get("duration_seconds") for item in attempts]
        paces = [item.get("metrics", {}).get("words_per_minute") for item in attempts]
        categories = Counter(
            item.get("category") or item.get("feedback", {}).get("question_type") or "general"
            for item in attempts
        )
        score_values: dict[str, list[float]] = defaultdict(list)
        fillers = 0
        total_minutes = 0.0
        for item in attempts:
            metrics = item.get("metrics", {})
            fillers += sum(metrics.get("filler_counts", {}).values())
            total_minutes += float(metrics.get("duration_seconds") or 0) / 60
            for name, value in item.get("feedback", {}).get("scores", {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    score_values[name].append(float(value))
        averages = {name: round(mean(values), 2) for name, values in score_values.items()}
        weaknesses = sorted(averages.items(), key=lambda item: item[1])[:3]
        comparisons = [item.get("comparison") for item in attempts if item.get("comparison")]
        behavioral = [
            item
            for item in attempts
            if (item.get("category") or item.get("feedback", {}).get("question_type"))
            == "behavioral"
        ]
        story_counts = Counter(_question_key(str(item.get("question", ""))) for item in behavioral)
        overused = [question for question, count in story_counts.items() if question and count >= 3]
        underdeveloped = [
            str(item.get("question"))
            for item in behavioral
            if (item.get("feedback", {}).get("scores", {}).get("star_completeness") or 5) < 3
        ]
        return {
            "attempts": len(attempts),
            "average_duration_seconds": _average(durations),
            "average_words_per_minute": _average(paces),
            "filler_words_per_minute": round(fillers / total_minutes, 2) if total_minutes else 0,
            "score_averages": averages,
            "star_component_coverage": averages.get("star_completeness"),
            "most_practiced_category": categories.most_common(1)[0][0] if categories else None,
            "weaknesses": weaknesses,
            "attempt_changes": comparisons,
            "overused_star_prompts": overused,
            "underdeveloped_star_prompts": list(dict.fromkeys(underdeveloped)),
        }

    def end_summary(self, entries: list[dict]) -> tuple[str, list[str]]:
        metrics = self.metrics(entries)
        if not metrics["attempts"]:
            return "No completed candidate attempts were recorded.", [
                "Complete one practice response."
            ]
        weaknesses = cast(list[tuple[str, float]], metrics["weaknesses"])
        summary = (
            f"{metrics['attempts']} attempt(s), averaging {metrics['average_duration_seconds'] or 0:.1f}s "
            f"at {metrics['average_words_per_minute'] or 0:.0f} wpm."
        )
        recommendations = [
            f"Practice {name.replace('_', ' ')} (current average {score}/5)."
            for name, score in weaknesses[:2]
        ]
        if cast(float, metrics["filler_words_per_minute"]) > 3:
            recommendations.append("Practice silent pauses to reduce filler words.")
        return summary, recommendations or ["Retry a question and compare the new attempt."]

    def metadata(self) -> dict:
        if not self.metadata_path.exists():
            return {"version": REVIEW_METADATA_VERSION, "questions": {}}
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": REVIEW_METADATA_VERSION, "questions": {}}
        return (
            data
            if isinstance(data, dict)
            else {"version": REVIEW_METADATA_VERSION, "questions": {}}
        )

    def update_question(self, question: str, *, note: str, marked: bool) -> None:
        data = self.metadata()
        data.setdefault("questions", {})[_question_key(question)] = {
            "question": question.strip(),
            "note": note.strip(),
            "marked": bool(marked),
        }
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def export_markdown(self, session: str | Path, output: Path, *, redact: bool = False) -> Path:
        entries = self.read(session)
        summary, recommendations = self.end_summary(entries)
        lines = [
            f"# Practice Session {self._resolve(session).stem}",
            "",
            summary,
            "",
            "## Recommendations",
            "",
        ]
        lines.extend(f"- {item}" for item in recommendations)
        for item in entries:
            if not item.get("question"):
                continue
            lines.extend(["", f"## {item['question']}", ""])
            if item.get("answer"):
                lines.extend(["### Coached answer", "", str(item["answer"])])
            if item.get("candidate_transcript"):
                lines.extend(["", "### Candidate response", "", str(item["candidate_transcript"])])
            feedback = item.get("feedback", {})
            if feedback.get("improved_answer"):
                lines.extend(["", "### Improved answer", "", str(feedback["improved_answer"])])
            for suggestion in feedback.get("improvements", []):
                lines.append(f"- {suggestion}")
        text = "\n".join(lines) + "\n"
        if redact:
            text = redact_personal_identifiers(text)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        return output

    def export_pdf(self, session: str | Path, output: Path, *, redact: bool = False) -> Path:
        # Qt is already a runtime dependency; keeping PDF generation here avoids
        # uploading private practice data to a conversion service.
        from PyQt6.QtGui import QTextDocument
        from PyQt6.QtPrintSupport import QPrinter

        markdown_path = Path(output).with_suffix(".export.md")
        self.export_markdown(session, markdown_path, redact=redact)
        document = QTextDocument()
        document.setMarkdown(markdown_path.read_text(encoding="utf-8"))
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output))
        document.print(printer)
        markdown_path.unlink(missing_ok=True)
        return Path(output)

    def cleanup(self, retention_days: int, *, now: datetime | None = None) -> list[Path]:
        if retention_days <= 0:
            return []
        cutoff = (now or datetime.now()) - timedelta(days=retention_days)
        deleted: list[Path] = []
        for path in self.paths():
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                path.unlink()
                audio = self.sessions_dir / "audio" / path.stem
                if audio.is_dir():
                    shutil.rmtree(audio)
                deleted.append(path)
        return deleted

    def delete_session(self, session: str | Path) -> None:
        path = self._resolve(session)
        path.unlink(missing_ok=True)
        audio = self.sessions_dir / "audio" / path.stem
        if audio.is_dir():
            shutil.rmtree(audio)

    def delete_all(self) -> None:
        if not self.sessions_dir.exists():
            return
        for path in self.paths():
            path.unlink()
        audio = self.sessions_dir / "audio"
        if audio.is_dir():
            shutil.rmtree(audio)
        self.metadata_path.unlink(missing_ok=True)

    def _resolve(self, session: str | Path) -> Path:
        value = Path(session)
        if value.parent != Path("."):
            path = value.resolve()
        else:
            name = value.name if value.suffix == ".jsonl" else value.name + ".jsonl"
            path = (self.sessions_dir / name).resolve()
        root = self.sessions_dir.resolve()
        if path.parent != root:
            raise ValueError("Session path must be directly inside the sessions directory.")
        return path


def redact_personal_identifiers(text: str) -> str:
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[REDACTED EMAIL]", text)
    text = re.sub(
        r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\w)",
        "[REDACTED PHONE]",
        text,
    )
    text = re.sub(
        r"\bhttps?://(?:www\.)?(?:linkedin\.com/in|github\.com)/[^\s)]+",
        "[REDACTED PROFILE]",
        text,
        flags=re.I,
    )
    return text


def _average(values: list[object]) -> float | None:
    numbers = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return round(mean(numbers), 2) if numbers else None


def _question_key(question: str) -> str:
    return " ".join(re.findall(r"\w+", question.casefold()))
