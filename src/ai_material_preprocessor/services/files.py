from __future__ import annotations

import re
from pathlib import Path

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_component(value: str, fallback: str = "未命名") -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", value.strip())
    cleaned = re.sub(r"\s+", "-", cleaned).strip(" ._-")
    return cleaned or fallback


def output_directory(source: Path, root: Path, category: str) -> Path:
    destination = root / category
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
