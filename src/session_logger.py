import json
import threading
import wave
from datetime import datetime
from pathlib import Path


class SessionLogger:
    def __init__(
        self,
        sessions_dir: Path,
        start_time: datetime | None = None,
        *,
        enabled: bool = True,
        audio_enabled: bool = False,
    ):
        self.enabled = enabled
        self.audio_enabled = audio_enabled
        self._lock = threading.Lock()
        self._audio_counter = 0
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
    ) -> None:
        if not self.enabled:
            return
        timestamp = timestamp or datetime.now()
        entry = {
            "timestamp": timestamp.isoformat(),
            "question": question,
            "answer": answer,
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
        entry = {
            "type": "candidate_attempt",
            "timestamp": datetime.now().isoformat(),
            "question": attempt.question,
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
