import json
import threading
import wave
from datetime import datetime
from pathlib import Path

from src.context_retrieval import classify_question
from src.session_repository import SESSION_SCHEMA_VERSION


class SessionLogger:
    def __init__(
        self,
        sessions_dir: Path,
        start_time: datetime | None = None,
        *,
        enabled: bool = True,
        audio_enabled: bool = False,
        profile: str | None = None,
        practice_mode: str = "learn",
    ):
        self.enabled = enabled
        self.audio_enabled = audio_enabled
        self.profile = profile
        self.practice_mode = practice_mode
        self._lock = threading.Lock()
        self._audio_counter = 0
        self._question_metadata: dict[str, tuple[str, str | None]] = {}
        self.sessions_dir = Path(sessions_dir)
        start_time = start_time or datetime.now()
        self.session_id = start_time.strftime("%Y%m%d-%H%M%S")
        filename = self.session_id + ".jsonl"
        self.path = self.sessions_dir / filename
        self.audio_dir = self.sessions_dir / "audio" / self.session_id
        if self.enabled or self.audio_enabled:
            self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        question: str,
        answer: str,
        timestamp: datetime | None = None,
        timings: dict | None = None,
        category: str | None = None,
        difficulty: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        timestamp = timestamp or datetime.now()
        question_key = " ".join(question.casefold().split())
        resolved_category = category or classify_question(question)
        with self._lock:
            self._question_metadata[question_key] = (resolved_category, difficulty)
        entry = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "type": "generated_answer",
            "timestamp": timestamp.isoformat(),
            "question": question,
            "answer": answer,
            "profile": self.profile,
            "practice_mode": self.practice_mode,
            "category": resolved_category,
            "difficulty": difficulty,
        }
        if timings is not None:
            entry["timings"] = timings
        self._append_entry(entry)

    def log_candidate_attempt(self, attempt) -> None:
        if not self.enabled:
            return
        feedback = attempt.feedback
        metrics = attempt.metrics
        comparison = attempt.comparison
        question_key = " ".join(attempt.question.casefold().split())
        with self._lock:
            category, difficulty = self._question_metadata.get(
                question_key,
                (classify_question(attempt.question), None),
            )
        entry = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "type": "candidate_attempt",
            "timestamp": datetime.now().isoformat(),
            "question": attempt.question,
            "profile": self.profile,
            "practice_mode": self.practice_mode,
            "category": category,
            "difficulty": difficulty,
            "attempt_number": attempt.attempt_number,
            "candidate_transcript": attempt.transcript,
            "transcription_confidence": attempt.transcription_confidence,
            "metrics": {
                "duration_seconds": metrics.duration_seconds,
                "word_count": metrics.word_count,
                "words_per_minute": metrics.words_per_minute,
                "filler_counts": dict(metrics.filler_counts),
                "repeated_phrases": list(metrics.repeated_phrases),
            },
            "feedback": {
                "question_type": feedback.question_type,
                "scores": feedback.scores,
                "facts": list(feedback.facts),
                "unsupported_claims": list(feedback.unsupported_claims),
                "missing_tradeoffs": list(feedback.missing_tradeoffs),
                "improvements": list(feedback.improvements),
                "improved_answer": feedback.improved_answer,
                "source": feedback.source,
            },
            "comparison": (
                {
                    "previous_attempt_number": comparison.previous_attempt_number,
                    "score_deltas": comparison.score_deltas,
                    "filler_delta": comparison.filler_delta,
                    "pace_delta": comparison.pace_delta,
                    "summary": comparison.summary,
                }
                if comparison
                else None
            ),
            "audio_path": attempt.audio_path,
        }
        self._append_entry(entry)

    def save_candidate_audio(self, pcm_bytes: bytes, sample_rate: int) -> str | None:
        if not self.audio_enabled:
            return None
        with self._lock:
            self._audio_counter += 1
            self.audio_dir.mkdir(parents=True, exist_ok=True)
            audio_path = self.audio_dir / f"candidate-{self._audio_counter:03d}.wav"
            with wave.open(str(audio_path), "wb") as audio_file:
                audio_file.setnchannels(1)
                audio_file.setsampwidth(2)
                audio_file.setframerate(sample_rate)
                audio_file.writeframes(pcm_bytes)
        return str(audio_path)

    def _append_entry(self, entry: dict) -> None:
        with self._lock:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(entry) + "\n")

    def read_all(self) -> list[dict]:
        if not self.enabled:
            return []
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
