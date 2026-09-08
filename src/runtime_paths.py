"""Choose a stable writable home for packaged builds."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def prepare_runtime_directory() -> Path:
    """Move packaged runs into Application Support and seed editable resources."""
    override = os.environ.get("INTERVIEW_HELPER_DATA_DIR")
    frozen = bool(getattr(sys, "frozen", False))
    if not frozen and not override:
        return Path.cwd()
    root = (
        Path(override).expanduser()
        if override
        else Path.home() / "Library" / "Application Support" / "Interview Helper"
    )
    root.mkdir(parents=True, exist_ok=True)
    resource_root = Path(getattr(sys, "_MEIPASS", Path.cwd()))
    for directory in ("skills", "templates"):
        source = resource_root / directory
        target = root / directory
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for item in source.rglob("*"):
                if item.is_file():
                    destination = target / item.relative_to(source)
                    if not destination.exists():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, destination)
    os.chdir(root)
    return root
