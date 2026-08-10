"""Private directory/file helpers (user-local data)."""

from __future__ import annotations

import os
from pathlib import Path

DIR_MODE = 0o700
FILE_MODE = 0o600


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, DIR_MODE)
    except OSError:
        pass
    return path


def write_private_text(path: Path, text: str) -> Path:
    ensure_private_dir(path.parent)
    path.write_text(text, encoding="utf-8")
    try:
        os.chmod(path, FILE_MODE)
    except OSError:
        pass
    return path
