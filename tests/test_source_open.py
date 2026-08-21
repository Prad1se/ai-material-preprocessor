from __future__ import annotations

import hashlib
from pathlib import Path

from ai_material_preprocessor.services.source_map import (
    SourceLocation,
    SourceMapEntry,
    SourceMapSource,
)
from ai_material_preprocessor.services.source_open import (
    SourceOpenCapability,
    resolve_source_open_target,
    source_paths_by_id,
)


def _source(path: Path, *, sha256: str | None = None) -> SourceMapSource:
    return SourceMapSource(
        source_id="source-001",
        source_order=1,
        display_name=path.name,
        source_format=path.suffix,
        provenance_level="page" if path.suffix.casefold() == ".pdf" else "document",
        sha256=sha256,
    )


def _entry(*, kind: str = "document", ordinal: int | None = None) -> SourceMapEntry:
    location = SourceLocation(
        kind=kind,
        label=f"page {ordinal}" if ordinal else "document",
        display=f"PDF page {ordinal}" if ordinal else "Document-level fallback",
        ordinal=ordinal,
        confidence=None,
        fallback=ordinal is None,
    )
    return SourceMapEntry(
        block_id="source-001-block-0001",
        source_id="source-001",
        source_order=1,
        block_order=1,
        heading_context=(),
        estimated_tokens=10,
        atomic=False,
        content="Content",
        content_sha256="a" * 64,
        content_verified=True,
        locations=(location,),
        primary_location=location,
    )


def _write_source(path: Path) -> str:
    content = b"original source"
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_resolve_pdf_page_location_when_source_identity_matches(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    digest = _write_source(path)

    target = resolve_source_open_target(
        _source(path, sha256=digest), _entry(kind="page", ordinal=37), path
    )

    assert target.capability is SourceOpenCapability.PAGE_LEVEL
    assert target.path == path
    assert target.page == 37
    assert target.available is True


def test_resolve_document_level_fallback_without_fake_precision(tmp_path: Path) -> None:
    path = tmp_path / "notes.docx"
    digest = _write_source(path)

    target = resolve_source_open_target(_source(path, sha256=digest), _entry(), path)

    assert target.capability is SourceOpenCapability.DOCUMENT_LEVEL
    assert target.page is None
    assert target.available is True


def test_resolve_missing_source_is_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "missing.pdf"

    target = resolve_source_open_target(_source(path), _entry(kind="page", ordinal=2), path)

    assert target.capability is SourceOpenCapability.UNAVAILABLE
    assert target.path is None
    assert "no longer available" in target.reason


def test_resolve_changed_source_is_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    _write_source(path)

    target = resolve_source_open_target(
        _source(path, sha256="0" * 64), _entry(kind="page", ordinal=4), path
    )

    assert target.capability is SourceOpenCapability.UNAVAILABLE
    assert target.path is None
    assert "changed" in target.reason


def test_resolve_rejects_candidate_with_wrong_filename(tmp_path: Path) -> None:
    expected = tmp_path / "paper.pdf"
    candidate = tmp_path / "different.pdf"
    _write_source(candidate)

    target = resolve_source_open_target(_source(expected), _entry(), candidate)

    assert target.capability is SourceOpenCapability.UNAVAILABLE
    assert target.path is None
    assert "does not match" in target.reason


def test_source_paths_are_paired_by_stable_order_even_with_duplicate_names(
    tmp_path: Path,
) -> None:
    first = tmp_path / "one" / "notes.pdf"
    second = tmp_path / "two" / "notes.pdf"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    sources = (
        SourceMapSource("source-002", 2, "notes.pdf", ".pdf", "page", None),
        SourceMapSource("source-001", 1, "notes.pdf", ".pdf", "page", None),
    )

    mapped = source_paths_by_id(sources, (first, second))

    assert mapped == {"source-001": first, "source-002": second}
