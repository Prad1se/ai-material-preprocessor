from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from ai_material_preprocessor.services.context_pack import ContextBudget, create_context_pack
from ai_material_preprocessor.services.document_provenance import ProvenanceKind, SourceSpan
from ai_material_preprocessor.services.source_map import load_source_map, source_map_to_dict


def _build_pack(
    tmp_path: Path,
    sources: list[tuple[str, str, tuple[SourceSpan, ...]]],
    *,
    budget: ContextBudget | None = None,
):
    contents = {
        f"source-{index:03d}": content
        for index, (_name, content, _spans) in enumerate(sources, start=1)
    }
    spans = {
        f"source-{index:03d}": value
        for index, (_name, _content, value) in enumerate(sources, start=1)
    }
    inputs: list[Path] = []
    for index, (name, _content, _spans) in enumerate(sources, start=1):
        source = tmp_path / "inputs" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"original-{index}", encoding="utf-8")
        inputs.append(source)

    def processor(source: Path, source_id: str, source_root: Path) -> Path:
        package = source_root / source_id
        package.mkdir(parents=True)
        (package / "raw.md").write_text("raw", encoding="utf-8")
        (package / "content.md").write_text(contents[source_id], encoding="utf-8")
        (package / "manifest.json").write_text(
            json.dumps(
                {
                    "source": {"name": source.name, "format": source.suffix, "sha256": "a" * 64},
                    "provenance": [span.to_dict() for span in spans[source_id]],
                    "warnings": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return package

    return create_context_pack(
        sources=tuple(inputs),
        output_root=tmp_path / "outputs",
        budget=budget or ContextBudget(None),
        source_processor=processor,
    )


def _pdf_page() -> tuple[str, str, tuple[SourceSpan, ...]]:
    return (
        "lecture.pdf",
        "<!-- Page: 37 -->\n\nPDF paragraph.",
        (SourceSpan(ProvenanceKind.PAGE, "第 37 页", 37, 1, 3),),
    )


def test_source_map_maps_block_to_pdf_page(tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])

    source_map = load_source_map(result.output_dir)

    assert source_map.version == 1
    assert source_map.integrity_ok is True
    assert any(
        entry.primary_location is not None
        and entry.primary_location.display == "PDF page 37"
        and entry.primary_location.fallback is False
        and entry.primary_location.ordinal == 37
        for entry in source_map.entries
    )


def test_source_map_maps_block_to_ppt_slide(tmp_path: Path) -> None:
    result = _build_pack(
        tmp_path,
        [
            (
                "slides.pptx",
                "<!-- Slide number: 18 -->\n\nSlide content.",
                (SourceSpan(ProvenanceKind.SLIDE, "幻灯片 18", 18, 1, 3),),
            )
        ],
    )

    source_map = load_source_map(result.output_dir)

    assert any(
        entry.primary_location is not None and entry.primary_location.display == "Slide 18"
        for entry in source_map.entries
    )


def test_source_map_maps_block_to_xlsx_worksheet(tmp_path: Path) -> None:
    result = _build_pack(
        tmp_path,
        [
            (
                "scores.xlsx",
                "# 工作表：成绩\n\n| 姓名 | 分数 |\n| --- | --- |\n| 小明 | 95 |\n",
                (SourceSpan(ProvenanceKind.WORKSHEET, "成绩", None, 1, 5),),
            )
        ],
    )

    source_map = load_source_map(result.output_dir)

    assert any(
        entry.primary_location is not None
        and entry.primary_location.display == "Sheet 成绩"
        and entry.primary_location.fallback is False
        for entry in source_map.entries
    )


def test_source_map_maps_ocr_with_confidence(tmp_path: Path) -> None:
    result = _build_pack(
        tmp_path,
        [
            (
                "scan.pdf",
                "### 第 2 页（平均置信度 62.0%）\n\n识别文字。",
                (SourceSpan(ProvenanceKind.OCR, "第 2 页", None, 1, 3, 0.62),),
            )
        ],
    )

    source_map = load_source_map(result.output_dir)

    locations = [location for entry in source_map.entries for location in entry.locations]
    assert any(location.kind == "ocr" and "62%" in location.display for location in locations)
    assert any(location.confidence == 0.62 for location in locations)


def test_source_map_uses_document_level_fallback_without_fabricating_pages(
    tmp_path: Path,
) -> None:
    result = _build_pack(
        tmp_path,
        [
            (
                "notes.docx",
                "# Notes\n\nPlain text.",
                (SourceSpan(ProvenanceKind.DOCUMENT, "Word 文档", None, 1, 3),),
            )
        ],
    )

    source_map = load_source_map(result.output_dir)

    locations = [location for entry in source_map.entries for location in entry.locations]
    assert locations
    assert all(location.fallback for location in locations)
    assert all(location.display == "Document-level fallback" for location in locations)
    assert all(location.ordinal is None for location in locations)
    assert all(entry.effective_display == "Document-level fallback" for entry in source_map.entries)


def test_source_map_entry_without_reliable_location_has_no_primary(tmp_path: Path) -> None:
    from ai_material_preprocessor.services.context_pack import (
        PreparedContextSource,
        build_context_plan,
        write_context_pack,
    )

    source = PreparedContextSource(
        source_id="source-001",
        source_order=1,
        display_name="plain.txt",
        source_format=".txt",
        content="Just text.",
        provenance=(SourceSpan(ProvenanceKind.PAGE, "第 9 页", 9, 100, 105),),
    )
    result = write_context_pack(
        build_context_plan((source,), ContextBudget(None)), tmp_path / "pack"
    )
    content_dir = result.output_dir / "sources" / "source-001"
    content_dir.mkdir(parents=True)
    (content_dir / "content.md").write_text("Just text.", encoding="utf-8")

    source_map = load_source_map(result.output_dir)

    assert source_map.integrity_ok is True
    assert all(entry.locations == () for entry in source_map.entries)
    assert all(entry.primary_location is None for entry in source_map.entries)
    assert all(entry.effective_display == "Document-level fallback" for entry in source_map.entries)


def test_source_map_rebuilds_block_content_and_verifies_sha256(tmp_path: Path) -> None:
    content = "# First\n\nAlpha paragraph.\n\n# Second\n\nBeta paragraph."
    result = _build_pack(
        tmp_path,
        [
            (
                "notes.md",
                content,
                (SourceSpan(ProvenanceKind.DOCUMENT, "Markdown 文档", None, 1, 6),),
            )
        ],
    )
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    expected_by_id = {block["block_id"]: block["content_sha256"] for block in manifest["blocks"]}

    source_map = load_source_map(result.output_dir)

    assert source_map.integrity_ok is True
    assert len(source_map.entries) == len(expected_by_id)
    for entry in source_map.entries:
        assert entry.content_sha256 == expected_by_id[entry.block_id]
        assert entry.content
        import hashlib

        assert hashlib.sha256(entry.content.encode("utf-8")).hexdigest() == entry.content_sha256


def test_source_map_degrades_gracefully_when_manifest_sha_does_not_match(tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    manifest_path = result.output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for block in manifest["blocks"]:
        block["content_sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    source_map = load_source_map(result.output_dir)

    assert source_map.integrity_ok is False
    assert all(not entry.content_verified for entry in source_map.entries)
    assert all(entry.content == "" for entry in source_map.entries)
    assert all(entry.effective_display for entry in source_map.entries)


def test_source_map_keeps_block_and_source_order_across_sources(tmp_path: Path) -> None:
    result = _build_pack(
        tmp_path,
        [
            (
                "first.pdf",
                "<!-- Page: 1 -->\n\nFirst.",
                (SourceSpan(ProvenanceKind.PAGE, "第 1 页", 1, 1, 3),),
            ),
            (
                "second.pdf",
                "<!-- Page: 2 -->\n\nSecond.",
                (SourceSpan(ProvenanceKind.PAGE, "第 2 页", 2, 1, 3),),
            ),
        ],
    )
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    expected_order = [block["block_id"] for block in manifest["blocks"]]

    source_map = load_source_map(result.output_dir)

    assert [entry.block_id for entry in source_map.entries] == expected_order
    assert source_map.entries[0].source_id == "source-001"
    assert source_map.entries[-1].source_id == "source-002"


def test_source_map_dict_never_leaks_private_or_temporary_paths(tmp_path: Path) -> None:
    private_root = tmp_path / "private" / "user-home"
    result = _build_pack(private_root, [_pdf_page()])

    payload = source_map_to_dict(load_source_map(result.output_dir))
    text = json.dumps(payload, ensure_ascii=False)

    assert str(private_root.resolve()) not in text
    assert str(result.output_dir.resolve()) not in text
    assert "\\Users" not in text
    assert "\\Temp" not in text


def test_source_map_reading_does_not_modify_pack_files(tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    before = {
        path.relative_to(result.output_dir).as_posix(): path.read_bytes()
        for path in result.output_dir.rglob("*")
        if path.is_file()
    }

    load_source_map(result.output_dir)

    after = {
        path.relative_to(result.output_dir).as_posix(): path.read_bytes()
        for path in result.output_dir.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_source_map_reads_old_context_pack_without_extra_files(tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])

    assert not (result.output_dir / "source-map.json").exists()
    source_map = load_source_map(result.output_dir)

    assert source_map.integrity_ok is True
    assert len(source_map.entries) >= 1


def test_source_map_rejects_missing_or_wrong_manifest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="manifest"):
        load_source_map(tmp_path / "missing")

    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / "manifest.json").write_text(
        json.dumps({"package_type": "ai_document_package", "format_version": 2}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Context Pack"):
        load_source_map(wrong)


def test_source_map_without_blocks_degrades_without_crashing(tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    manifest_path = result.output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["blocks"] = []
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    source_map = load_source_map(result.output_dir)

    assert source_map.entries == ()
    assert source_map.integrity_ok is False


def test_source_map_version_is_independent_from_context_pack_version(tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    manifest_path = result.output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["context_pack_version"] = 7
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    source_map = load_source_map(result.output_dir)

    assert source_map.version == 1


def test_source_map_does_not_read_content_outside_pack_sources(tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    outside_dir = tmp_path / "private"
    outside_dir.mkdir()
    outside_content = "private material must not be loaded"
    (outside_dir / "content.md").write_text(outside_content, encoding="utf-8")
    escaped_source_id = os.path.relpath(outside_dir, result.output_dir / "sources")

    manifest_path = result.output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sources"][0]["source_id"] = escaped_source_id
    manifest["blocks"][0]["source_id"] = escaped_source_id
    manifest["blocks"][0]["content_sha256"] = hashlib.sha256(
        outside_content.encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    source_map = load_source_map(result.output_dir)

    assert source_map.integrity_ok is False
    assert all(entry.content == "" for entry in source_map.entries)
    assert all(not entry.content_verified for entry in source_map.entries)


def test_source_map_duplicate_manifest_blocks_degrade_integrity(tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    manifest_path = result.output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["blocks"].append(dict(manifest["blocks"][0]))
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    source_map = load_source_map(result.output_dir)

    assert source_map.integrity_ok is False


def test_source_map_malformed_integrity_fields_degrade_without_crashing(tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    manifest_path = result.output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["integrity"]["status"] = []
    manifest["integrity"]["missing_blocks"] = []
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    source_map = load_source_map(result.output_dir)

    assert source_map.integrity_ok is False
