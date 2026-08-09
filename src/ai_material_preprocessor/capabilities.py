from __future__ import annotations

from pathlib import Path

from .converters.markdown import SUPPORTED_EXTENSIONS as MARKDOWN_EXTENSIONS
from .converters.office_pdf import POWERPOINT_EXTENSIONS, WORD_EXTENSIONS
from .converters.video import VIDEO_EXTENSIONS
from .models import Operation, ToolStatus


def _available(tools: dict[str, ToolStatus], name: str) -> bool:
    return bool(tools.get(name) and tools[name].available)


def available_operations(filename: str | Path, tools: dict[str, ToolStatus]) -> list[Operation]:
    suffix = Path(filename).suffix.lower()
    operations: list[Operation] = []

    if suffix in MARKDOWN_EXTENSIONS and _available(tools, "markitdown"):
        operations.append(Operation.TO_MARKDOWN)

    if (
        suffix in WORD_EXTENSIONS
        and (_available(tools, "winword") or _available(tools, "libreoffice"))
        or suffix in POWERPOINT_EXTENSIONS
        and (_available(tools, "powerpoint") or _available(tools, "libreoffice"))
    ):
        operations.append(Operation.TO_PDF)

    if suffix in VIDEO_EXTENSIONS:
        if _available(tools, "ffmpeg"):
            operations.extend(
                [
                    Operation.COMPRESS_VIDEO,
                    Operation.EXTRACT_AUDIO,
                    Operation.STANDARDIZE_MP4,
                    Operation.KEYFRAMES_CONTACT_SHEET,
                ]
            )
        operations.append(Operation.RENAME_VIDEO)

    return operations
