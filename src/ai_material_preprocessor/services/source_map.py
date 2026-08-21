"""Source Map v1: read-only mapping from Context Pack blocks back to original sources.

This module only *reads* an existing Context Pack (`manifest.json`) and derives a
deterministic, privacy-safe Source Map. It never writes into the pack, never modifies
the Context Pack schema, and never fabricates a finer provenance level than the
existing document pipeline already provides (PDF page, PPTX slide, XLSX worksheet,
OCR page label, or document-level fallback).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .context_pack import STABLE_FRAGMENT_TOKENS
from .document_provenance import ProvenanceKind
from .markdown_splitting import split_oversized_markdown_block, structured_markdown_blocks

SOURCE_MAP_VERSION = 1
DOCUMENT_LEVEL_DISPLAY = "Document-level fallback"


@dataclass(frozen=True)
class SourceLocation:
    kind: str
    label: str
    display: str
    ordinal: int | None
    confidence: float | None
    fallback: bool


@dataclass(frozen=True)
class SourceMapSource:
    source_id: str
    source_order: int
    display_name: str
    source_format: str
    provenance_level: str
    sha256: str | None


@dataclass(frozen=True)
class SourceMapEntry:
    block_id: str
    source_id: str
    source_order: int
    block_order: int
    heading_context: tuple[str, ...]
    estimated_tokens: int
    atomic: bool
    content: str
    content_sha256: str
    content_verified: bool
    locations: tuple[SourceLocation, ...]
    primary_location: SourceLocation | None

    @property
    def effective_display(self) -> str:
        return (
            self.primary_location.display
            if self.primary_location is not None
            else DOCUMENT_LEVEL_DISPLAY
        )


@dataclass(frozen=True)
class SourceMap:
    version: int
    sources: tuple[SourceMapSource, ...]
    entries: tuple[SourceMapEntry, ...]
    integrity_ok: bool

    @property
    def degraded(self) -> bool:
        return not self.integrity_ok


def _display_for(
    kind: ProvenanceKind, label: str, ordinal: int | None, confidence: float | None
) -> str:
    if kind is ProvenanceKind.PAGE:
        return f"PDF page {ordinal}" if ordinal is not None else DOCUMENT_LEVEL_DISPLAY
    if kind is ProvenanceKind.SLIDE:
        return f"Slide {ordinal}" if ordinal is not None else DOCUMENT_LEVEL_DISPLAY
    if kind is ProvenanceKind.WORKSHEET:
        return f"Sheet {label}" if label else DOCUMENT_LEVEL_DISPLAY
    if kind is ProvenanceKind.OCR:
        base = f"OCR {label}" if label else "OCR"
        return f"{base} ({confidence:.0%} confidence)" if confidence is not None else base
    return DOCUMENT_LEVEL_DISPLAY


def _fallback_for(kind: ProvenanceKind, ordinal: int | None, label: str) -> bool:
    return (
        kind is ProvenanceKind.DOCUMENT
        or (kind in {ProvenanceKind.PAGE, ProvenanceKind.SLIDE} and ordinal is None)
        or (kind is ProvenanceKind.WORKSHEET and not label)
    )


def _location_from_span(payload: dict[str, object], *, source_format: str) -> SourceLocation:
    del source_format
    raw_kind = payload.get("source_type", "document")
    try:
        kind = ProvenanceKind(str(raw_kind))
    except ValueError:
        kind = ProvenanceKind.DOCUMENT
    label = str(payload.get("label") or "")
    raw_ordinal = payload.get("ordinal")
    ordinal = (
        int(raw_ordinal)
        if isinstance(raw_ordinal, int | str) and str(raw_ordinal).strip()
        else None
    )
    raw_confidence = payload.get("confidence")
    confidence = float(raw_confidence) if isinstance(raw_confidence, int | float) else None
    return SourceLocation(
        kind=kind.value,
        label=label,
        display=_display_for(kind, label, ordinal, confidence),
        ordinal=ordinal,
        confidence=confidence,
        fallback=_fallback_for(kind, ordinal, label),
    )


def _primary_location(locations: tuple[SourceLocation, ...]) -> SourceLocation | None:
    for location in locations:
        if not location.fallback:
            return location
    return locations[0] if locations else None


def _derived_content_blocks(content: str) -> list[str]:
    blocks: list[str] = []
    for structured in structured_markdown_blocks(content):
        pieces = (
            (structured.content,)
            if structured.atomic
            else split_oversized_markdown_block(structured.content, STABLE_FRAGMENT_TOKENS)
        )
        blocks.extend(pieces)
    return blocks


def _source_from_manifest(payload: dict[str, object]) -> SourceMapSource:
    raw_sha = payload.get("sha256")
    raw_order = payload.get("order")
    return SourceMapSource(
        source_id=str(payload.get("source_id") or ""),
        source_order=int(raw_order)
        if isinstance(raw_order, int | str) and str(raw_order).strip()
        else 0,
        display_name=str(payload.get("display_name") or payload.get("source_id") or ""),
        source_format=str(payload.get("format") or ""),
        provenance_level=str(payload.get("provenance_level") or "document"),
        sha256=str(raw_sha) if raw_sha else None,
    )


def _entries_from_manifest(
    pack_dir: Path, raw_blocks: list[object], source_by_id: dict[str, SourceMapSource]
) -> tuple[SourceMapEntry, ...]:
    derived: dict[str, list[str]] = {}
    for source_id in source_by_id:
        content_path = pack_dir / "sources" / source_id / "content.md"
        derived[source_id] = (
            _derived_content_blocks(content_path.read_text(encoding="utf-8"))
            if content_path.is_file()
            else []
        )
    entries: list[SourceMapEntry] = []
    for raw in raw_blocks:
        if not isinstance(raw, dict):
            continue
        block_id = str(raw.get("block_id") or "")
        source_id = str(raw.get("source_id") or "")
        source = source_by_id.get(source_id)
        block_order = int(raw.get("block_order") or 1)
        manifest_sha = str(raw.get("content_sha256") or "")
        pieces = derived.get(source_id, [])
        expected = pieces[block_order - 1] if 1 <= block_order <= len(pieces) else None
        content = ""
        verified = False
        if expected is not None:
            digest = hashlib.sha256(expected.encode("utf-8")).hexdigest()
            if manifest_sha and digest == manifest_sha:
                content = expected
                verified = True
        locations = tuple(
            _location_from_span(item, source_format=source.source_format if source else "")
            for item in raw.get("provenance") or []
            if isinstance(item, dict)
        )
        entries.append(
            SourceMapEntry(
                block_id=block_id,
                source_id=source_id,
                source_order=source.source_order if source else 0,
                block_order=block_order,
                heading_context=tuple(
                    str(item) for item in (raw.get("heading_context") or []) if item
                ),
                estimated_tokens=int(raw.get("estimated_tokens") or 0),
                atomic=bool(raw.get("atomic")),
                content=content,
                content_sha256=manifest_sha,
                content_verified=verified,
                locations=locations,
                primary_location=_primary_location(locations),
            )
        )
    return tuple(entries)


def load_source_map(pack_dir: Path) -> SourceMap:
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Context Pack manifest is missing.")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Context Pack manifest is invalid.")
    if payload.get("package_type") != "ai_context_pack":
        raise ValueError("Not an AI Context Pack.")
    try:
        version = int(payload.get("context_pack_version") or 1)
    except (TypeError, ValueError):
        version = 1
    sources = tuple(
        _source_from_manifest(item)
        for item in payload.get("sources") or []
        if isinstance(item, dict)
    )
    source_by_id = {source.source_id: source for source in sources}
    entries = _entries_from_manifest(pack_dir, list(payload.get("blocks") or []), source_by_id)
    integrity_ok = bool(entries) and all(entry.content_verified for entry in entries)
    return SourceMap(version=version, sources=sources, entries=entries, integrity_ok=integrity_ok)


def source_map_to_dict(source_map: SourceMap) -> dict[str, object]:
    return {
        "version": source_map.version,
        "integrity": "complete" if source_map.integrity_ok else "degraded",
        "sources": [
            {
                "source_id": source.source_id,
                "display_name": source.display_name,
                "format": source.source_format,
                "provenance_level": source.provenance_level,
                "sha256": source.sha256,
            }
            for source in source_map.sources
        ],
        "entries": [
            {
                "block_id": entry.block_id,
                "source_id": entry.source_id,
                "source_order": entry.source_order,
                "block_order": entry.block_order,
                "heading_context": list(entry.heading_context),
                "estimated_tokens": entry.estimated_tokens,
                "atomic": entry.atomic,
                "content_sha256": entry.content_sha256,
                "content_verified": entry.content_verified,
                "primary_location": entry.primary_location.display
                if entry.primary_location is not None
                else None,
                "effective_display": entry.effective_display,
                "locations": [
                    {
                        "kind": location.kind,
                        "label": location.label,
                        "display": location.display,
                        "ordinal": location.ordinal,
                        "confidence": location.confidence,
                        "fallback": location.fallback,
                    }
                    for location in entry.locations
                ],
            }
            for entry in source_map.entries
        ],
    }
