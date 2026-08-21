from __future__ import annotations

from collections.abc import Iterable, Set
from pathlib import Path

from ..converters.markdown import SUPPORTED_EXTENSIONS as MARKDOWN_EXTENSIONS
from ..converters.office_pdf import POWERPOINT_EXTENSIONS, WORD_EXTENSIONS
from ..converters.video import VIDEO_EXTENSIONS

SUPPORTED_INPUT_EXTENSIONS = frozenset(
    MARKDOWN_EXTENSIONS | WORD_EXTENSIONS | POWERPOINT_EXTENSIONS | VIDEO_EXTENSIONS
)


def discover_input_files(
    paths: Iterable[str | Path],
    *,
    supported_extensions: Set[str] | None = None,
) -> list[Path]:
    """Expand dropped files and folders into a deterministic, de-duplicated input list."""
    allowed = (
        SUPPORTED_INPUT_EXTENSIONS
        if supported_extensions is None
        else frozenset(
            extension.lower() if extension.startswith(".") else f".{extension.lower()}"
            for extension in supported_extensions
        )
    )
    discovered: dict[str, Path] = {}
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        candidates: Iterable[Path]
        if path.is_file():
            candidates = (path,)
        elif path.is_dir():
            try:
                candidates = sorted(
                    (candidate for candidate in path.rglob("*") if candidate.is_file()),
                    key=lambda candidate: str(candidate).casefold(),
                )
            except OSError:
                continue
        else:
            continue
        for candidate in candidates:
            if candidate.suffix.lower() not in allowed:
                continue
            resolved = candidate.resolve()
            discovered.setdefault(str(resolved).casefold(), resolved)
    return sorted(discovered.values(), key=lambda candidate: str(candidate).casefold())
