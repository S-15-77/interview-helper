"""Structured local diagnostics with a privacy-conscious support export."""

from __future__ import annotations

import json
import logging
import platform
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            },
            ensure_ascii=False,
        )


def configure_logging(log_dir: Path = Path("logs")) -> Path:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "interview-helper.jsonl"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("interview_helper")
    root.setLevel(logging.INFO)
    if not any(
        isinstance(item, logging.FileHandler) and Path(item.baseFilename) == path.resolve()
        for item in root.handlers
    ):
        root.addHandler(handler)
    return path


def export_troubleshooting_bundle(
    output: Path,
    *,
    log_path: Path = Path("logs/interview-helper.jsonl"),
    settings_path: Path = Path("my_data/settings.json"),
) -> Path:
    """Export diagnostics only; resume/profile/session content is deliberately excluded."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "includes_private_profile_or_session_data": False,
    }
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.json", json.dumps(manifest, indent=2))
        if Path(log_path).exists():
            archive.write(log_path, "interview-helper.jsonl")
        if Path(settings_path).exists():
            try:
                settings = json.loads(Path(settings_path).read_text(encoding="utf-8"))
                audio = settings.get("audio", {})
                audio.pop("device_name", None)
                audio.pop("candidate_device_name", None)
                archive.writestr("settings-redacted.json", json.dumps(settings, indent=2))
            except (OSError, json.JSONDecodeError):
                pass
    return output
