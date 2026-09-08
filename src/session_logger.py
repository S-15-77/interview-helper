import json
from datetime import datetime
from pathlib import Path


class SessionLogger:
    def __init__(
        self,
        sessions_dir: Path,
        start_time: datetime | None = None,
        *,
        enabled: bool = True,
    ):
        self.enabled = enabled
        self.sessions_dir = Path(sessions_dir)
        start_time = start_time or datetime.now()
        filename = start_time.strftime("%Y%m%d-%H%M%S") + ".jsonl"
        self.path = self.sessions_dir / filename
        if self.enabled:
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
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def read_all(self) -> list[dict]:
        if not self.enabled:
            return []
        if not self.path.exists():
            return []
        with self.path.open() as f:
            return [json.loads(line) for line in f if line.strip()]
