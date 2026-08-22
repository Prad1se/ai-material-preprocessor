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
        return _unavailable(source, "Original source location is unavailable in this session.")
    try:
        candidate = candidate_path.resolve()
    except (OSError, RuntimeError):
        return _unavailable(source, "Original source location is unavailable in this session.")
    if not candidate.is_file():
        return _unavailable(source, "The original source file is no longer available.")
    if candidate.name.casefold() != source.display_name.casefold():
        return _unavailable(source, "The available file does not match the recorded source name.")

    expected_sha = (source.sha256 or "").strip().casefold()
    if expected_sha:
        if len(expected_sha) != 64 or any(char not in "0123456789abcdef" for char in expected_sha):
            return _unavailable(source, "The recorded source identity cannot be verified.")
        try:
            if _sha256(candidate).casefold() != expected_sha:
                return _unavailable(
                    source, "The original source file has changed since processing."
                )
        except OSError:
            return _unavailable(source, "The original source file cannot be read.")

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
            reason="Page-level location (viewer permitting).",
        )
    return SourceOpenTarget(
        source_id=source.source_id,
        path=candidate,
        capability=SourceOpenCapability.DOCUMENT_LEVEL,
        page=None,
        reason="Document-level location.",
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
