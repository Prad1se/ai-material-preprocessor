"""Runtime-only resolution of Source Map entries to local source files.

Local paths never enter the Context Pack or Source Map serialization. The resolver
only accepts a candidate supplied by the current application session and verifies
its filename and, when available, the source SHA-256 recorded by the pack.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .source_map import SourceMapEntry, SourceMapSource


class SourceOpenCapability(StrEnum):
    PAGE_LEVEL = "page_level"
    DOCUMENT_LEVEL = "document_level"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SourceOpenTarget:
    source_id: str
    path: Path | None
    capability: SourceOpenCapability
    page: int | None
    reason: str

    @property
    def available(self) -> bool:
        return self.path is not None and self.capability is not SourceOpenCapability.UNAVAILABLE


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unavailable(source: SourceMapSource, reason: str) -> SourceOpenTarget:
    return SourceOpenTarget(
        source_id=source.source_id,
        path=None,
        capability=SourceOpenCapability.UNAVAILABLE,
        page=None,
        reason=reason,
    )


def resolve_source_open_target(
    source: SourceMapSource,
    entry: SourceMapEntry,
    candidate_path: Path | None,
) -> SourceOpenTarget:
    """Resolve a verified local file without claiming unsupported precision."""
    if candidate_path is None:
        return _unavailable(source, "当前会话中没有原始来源位置。")
    try:
        candidate = candidate_path.resolve()
    except (OSError, RuntimeError):
        return _unavailable(source, "当前会话中没有原始来源位置。")
    if not candidate.is_file():
        return _unavailable(source, "原始来源文件已不可用。")
    if candidate.name.casefold() != source.display_name.casefold():
        return _unavailable(source, "当前文件与记录的来源名称不匹配。")

    expected_sha = (source.sha256 or "").strip().casefold()
    if expected_sha:
        if len(expected_sha) != 64 or any(char not in "0123456789abcdef" for char in expected_sha):
            return _unavailable(source, "无法验证记录的来源标识。")
        try:
            if _sha256(candidate).casefold() != expected_sha:
                return _unavailable(source, "原始来源文件在处理后已发生变化。")
        except OSError:
            return _unavailable(source, "无法读取原始来源文件。")

    location = entry.primary_location
    is_pdf = source.source_format.casefold().lstrip(".") == "pdf"
    if (
        is_pdf
        and location is not None
        and location.kind == "page"
        and location.ordinal is not None
        and location.ordinal > 0
    ):
        return SourceOpenTarget(
            source_id=source.source_id,
            path=candidate,
            capability=SourceOpenCapability.PAGE_LEVEL,
            page=location.ordinal,
            reason="页级定位（取决于查看器）。",
        )
    return SourceOpenTarget(
        source_id=source.source_id,
        path=candidate,
        capability=SourceOpenCapability.DOCUMENT_LEVEL,
        page=None,
        reason="文档级定位。",
    )


def source_paths_by_id(
    sources: tuple[SourceMapSource, ...], candidates: tuple[Path, ...]
) -> dict[str, Path]:
    """Pair current-session paths to stable source IDs by recorded source order."""
    ordered = sorted(sources, key=lambda source: source.source_order)
    return {
        source.source_id: candidates[index]
        for index, source in enumerate(ordered)
        if index < len(candidates) and source.source_id
    }
