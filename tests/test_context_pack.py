from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_material_preprocessor.services.context_pack import (
    ContextBudget,
    PreparedContextSource,
    assign_source_ids,
    build_context_plan,
    create_context_pack,
    write_context_pack,
)
from ai_material_preprocessor.services.document_provenance import (
    ProvenanceKind,
    SourceSpan,
)
from ai_material_preprocessor.services.markdown_splitting import estimate_tokens


def _source(
    source_id: str,
    order: int,
    content: str,
    *,
    name: str | None = None,
    provenance: tuple[SourceSpan, ...] = (),
) -> PreparedContextSource:
    return PreparedContextSource(
        source_id=source_id,
        source_order=order,
        display_name=name or f"lesson-{order}.md",
        source_format=".md",
        content=content,
        provenance=provenance,
    )


@pytest.mark.parametrize(
    "text",
    [
        "An English sentence with headings and punctuation.",
        "这是一段用于估算的中文内容。",
        "中英 mixed context with Markdown # headings.",
        "| column | value |\n| --- | --- |\n| one | two |",
        "```python\nprint('context')\n```",
        "OCR 第 3 页 置信度 82.5% noisy-text",
    ],
)
def test_existing_token_estimator_is_deterministic_and_model_independent(text: str) -> None:
    first = estimate_tokens(text)

    assert first > 0
    assert estimate_tokens(text) == first


def test_context_budget_validates_custom_values_and_reserves_header_space() -> None:
    assert ContextBudget(None).soft_target_tokens is None
    assert ContextBudget(32_000).soft_target_tokens == 30_400

    with pytest.raises(ValueError, match="positive integer"):
        ContextBudget(0)
    with pytest.raises(ValueError, match="at least 1000"):
        ContextBudget(999)
    with pytest.raises(ValueError, match="at most"):
        ContextBudget(10_000_001)


def test_stable_source_ids_use_input_order_and_do_not_depend_on_paths(tmp_path: Path) -> None:
    first = tmp_path / "one" / "相同名称.pdf"
    second = tmp_path / "two" / "相同名称.pdf"

    assigned = assign_source_ids((first, second))

    assert assigned == (("source-001", first), ("source-002", second))
    assert all(str(tmp_path) not in source_id for source_id, _path in assigned)


def test_no_limit_creates_one_pack_and_preserves_all_blocks_once() -> None:
    sources = (
        _source("source-001", 1, "# First\n\nAlpha.\n\nBeta."),
        _source("source-002", 2, "# Second\n\nGamma.\n\nDelta."),
    )

    plan = build_context_plan(sources, ContextBudget(None))

    assert len(plan.packs) == 1
    assert plan.packs[0].over_budget is False
    assert plan.integrity.input_blocks == plan.integrity.packed_blocks
    assert plan.integrity.missing_block_ids == ()
    assert plan.integrity.duplicate_block_ids == ()
    assert [block.block_id for block in plan.blocks] == [
        block_id for pack in plan.packs for block_id in pack.block_ids
    ]


def test_budget_splits_deterministically_without_missing_or_duplicate_blocks() -> None:
    content = "# Notes\n\n" + "\n\n".join(
        f"Section {index}. " + "word " * 230 for index in range(1, 13)
    )
    source = _source("source-001", 1, content)

    first = build_context_plan((source,), ContextBudget(1_000))
    second = build_context_plan((source,), ContextBudget(1_000))

    assert len(first.packs) >= 2
    assert [pack.block_ids for pack in first.packs] == [pack.block_ids for pack in second.packs]
    packed = [block_id for pack in first.packs for block_id in pack.block_ids]
    assert packed == [block.block_id for block in first.blocks]
    assert len(packed) == len(set(packed))
    assert first.integrity.complete is True
    assert all(pack.estimated_tokens <= 1_000 for pack in first.packs if not pack.over_budget)


def test_atomic_overflow_is_kept_whole_and_reported() -> None:
    table = "| column | value |\n| --- | --- |\n" + "\n".join(
        f"| row-{index} | {'word ' * 30} |" for index in range(80)
    )
    plan = build_context_plan(
        (_source("source-001", 1, f"# Large table\n\n{table}"),),
        ContextBudget(1_000),
    )

    overflow = [pack for pack in plan.packs if pack.over_budget]
    assert len(overflow) == 1
    assert "atomic" in overflow[0].overflow_reason.lower()
    packed_content = "\n".join(
        block.content for block in plan.blocks if block.block_id in overflow[0].block_ids
    )
    assert table in packed_content
    assert plan.integrity.complete is True


@pytest.mark.parametrize(
    "content",
    [
        "Before fence without blank line\n```python\nprint('kept whole.')\n```",
        "| Column. | Value. |\n| --- | --- |\n| Sentence. | Still one table. |",
    ],
)
def test_structural_atomic_blocks_are_not_split_at_budget_boundaries(content: str) -> None:
    plan = build_context_plan((_source("source-001", 1, content),), ContextBudget(1_000))

    atomic = [block for block in plan.blocks if block.atomic]
    assert len(atomic) == 1
    assert atomic[0].content in content
    assert sum(atomic[0].block_id in pack.block_ids for pack in plan.packs) == 1


def test_four_backtick_fence_is_not_closed_by_nested_triple_backticks() -> None:
    content = "````markdown\n```python\nprint('nested')\n```\n" + "word " * 1200 + "\n````"

    plan = build_context_plan((_source("source-001", 1, content),), ContextBudget(1_000))

    assert len(plan.blocks) == 1
    assert plan.blocks[0].atomic is True
    assert plan.blocks[0].content == content
    assert plan.packs[0].over_budget is True


def test_provenance_and_stable_block_ids_survive_multi_source_assembly() -> None:
    sources = (
        _source(
            "source-001",
            1,
            "<!-- Page: 7 -->\n\nPDF paragraph.",
            name="lecture.pdf",
            provenance=(SourceSpan(ProvenanceKind.PAGE, "第 7 页", 7, 1, 3),),
        ),
        _source(
            "source-002",
            2,
            "<!-- Slide number: 3 -->\n\nSlide paragraph.",
            name="slides.pptx",
            provenance=(SourceSpan(ProvenanceKind.SLIDE, "幻灯片 3", 3, 1, 3),),
        ),
    )

    plan = build_context_plan(sources, ContextBudget(None))

    assert [block.block_id for block in plan.blocks] == sorted(
        block.block_id for block in plan.blocks
    )
    refs = [ref for block in plan.blocks for ref in block.provenance_refs]
    assert any(ref.label == "第 7 页" for ref in refs)
    assert any(ref.label == "幻灯片 3" for ref in refs)


@pytest.mark.parametrize(
    ("kind", "label"),
    [
        (ProvenanceKind.PAGE, "第 7 页"),
        (ProvenanceKind.SLIDE, "幻灯片 3"),
        (ProvenanceKind.WORKSHEET, "工作表 Data"),
        (ProvenanceKind.DOCUMENT, "Word 文档"),
        (ProvenanceKind.OCR, "OCR 第 2 页"),
    ],
)
def test_context_manifest_preserves_existing_provenance_levels(
    tmp_path: Path, kind: ProvenanceKind, label: str
) -> None:
    source = _source(
        "source-001",
        1,
        "# Content\n\nTraceable text.",
        provenance=(SourceSpan(kind, label, 2, 1, 3, 0.82),),
    )

    result = write_context_pack(
        build_context_plan((source,), ContextBudget(None)), tmp_path / kind.value
    )
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))

    refs = [ref for block in manifest["blocks"] for ref in block["provenance"]]
    assert any(ref["source_type"] == kind.value and ref["label"] == label for ref in refs)


def test_writer_creates_self_describing_private_package(tmp_path: Path) -> None:
    private_root = tmp_path / "private" / "user-home"
    source_path = private_root / "课程资料.docx"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("original", encoding="utf-8")
    sources = (
        _source(
            "source-001",
            1,
            "# 课程\n\n完整内容。",
            name=source_path.name,
            provenance=(SourceSpan(ProvenanceKind.DOCUMENT, "Word 文档", None, 1, 3),),
        ),
    )
    plan = build_context_plan(sources, ContextBudget(32_000))
    output = tmp_path / "AI-Context-Pack"

    result = write_context_pack(plan, output)

    assert result.output_dir == output
    assert result.start_here.is_file()
    assert result.content.is_file()
    assert result.manifest.is_file()
    assert result.context_report.is_file()
    assert [path.name for path in result.packs] == ["001-context.md"]
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    report = json.loads(result.context_report.read_text(encoding="utf-8"))
    assert manifest["package_type"] == "ai_context_pack"
    assert manifest["context_pack_version"] == 1
    assert report["integrity"] == {
        "input_blocks": len(plan.blocks),
        "packed_blocks": len(plan.blocks),
        "missing_blocks": 0,
        "missing_block_ids": [],
        "duplicate_blocks": 0,
        "duplicate_block_ids": [],
        "order_preserved": True,
        "status": "complete",
    }
    public_text = "\n".join(
        path.read_text(encoding="utf-8") for path in output.rglob("*") if path.is_file()
    )
    assert str(private_root) not in public_text
    assert "No source content was intentionally removed." in result.start_here.read_text(
        encoding="utf-8"
    )


def test_real_orchestrator_builds_unique_multi_source_package_from_existing_source_packages(
    tmp_path: Path,
) -> None:
    sources = tuple(tmp_path / "inputs" / name for name in ("一.txt", "二.txt", "三.txt"))
    for index, source in enumerate(sources, start=1):
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"original-{index}", encoding="utf-8")
    original = {source: source.read_bytes() for source in sources}

    def processor(source: Path, source_id: str, source_root: Path) -> Path:
        package = source_root / source_id
        package.mkdir(parents=True)
        (package / "raw.md").write_text(f"raw source at {source.resolve()}", encoding="utf-8")
        (package / "content.md").write_text(
            f"# {source.name}\n\n<!-- Page: 1 -->\n\n" + "word " * 500,
            encoding="utf-8",
        )
        (package / "manifest.json").write_text(
            json.dumps(
                {
                    "source": {
                        "name": source.name,
                        "format": source.suffix,
                        "sha256": "a" * 64,
                    },
                    "provenance": [
                        {
                            "source_type": "page",
                            "label": "第 1 页",
                            "ordinal": 1,
                            "start_line": 1,
                            "end_line": 5,
                            "confidence": None,
                        }
                    ],
                    "warnings": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return package

    first = create_context_pack(
        sources=sources,
        output_root=tmp_path / "outputs",
        budget=ContextBudget(1_000),
        source_processor=processor,
    )
    second = create_context_pack(
        sources=sources,
        output_root=tmp_path / "outputs",
        budget=ContextBudget(1_000),
        source_processor=processor,
    )

    assert first.output_dir != second.output_dir
    assert len(first.packs) >= 2
    assert {path.name for path in first.output_dir.joinpath("sources").iterdir()} == {
        "source-001",
        "source-002",
        "source-003",
    }
    assert all(source.read_bytes() == original[source] for source in sources)
    public = "\n".join(
        path.read_text(encoding="utf-8") for path in first.output_dir.rglob("*") if path.is_file()
    )
    assert str(tmp_path.resolve()) not in public
    report = json.loads(first.context_report.read_text(encoding="utf-8"))
    assert report["integrity"]["status"] == "complete"
    assert report["source_count"] == 3


def test_source_export_rewrites_asset_links_for_archive_and_packs(tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.write_text("original", encoding="utf-8")

    def processor(_source: Path, source_id: str, source_root: Path) -> Path:
        package = source_root / source_id
        assets = package / "assets"
        assets.mkdir(parents=True)
        (assets / "diagram.png").write_bytes(b"image")
        (package / "raw.md").write_text("raw", encoding="utf-8")
        (package / "content.md").write_text(
            "# Diagram\n\n![figure](assets/diagram.png)", encoding="utf-8"
        )
        (package / "manifest.json").write_text(
            json.dumps({"source": {"name": source.name}, "warnings": []}),
            encoding="utf-8",
        )
        return package

    result = create_context_pack(
        sources=(source,),
        output_root=tmp_path / "outputs",
        budget=ContextBudget(None),
        source_processor=processor,
    )

    assert "(sources/source-001/assets/diagram.png)" in result.content.read_text(encoding="utf-8")
    assert "(../sources/source-001/assets/diagram.png)" in result.packs[0].read_text(
        encoding="utf-8"
    )
    assert (result.output_dir / "sources/source-001/assets/diagram.png").is_file()


def test_asset_link_rewrite_does_not_modify_code_examples(tmp_path: Path) -> None:
    source = _source(
        "source-001",
        1,
        "# Examples\n\n`![inline](assets/example.png)`\n\n"
        "```markdown\n![fenced](assets/example.png)\n```\n\n"
        "![real](assets/example.png)",
    )

    result = write_context_pack(
        build_context_plan((source,), ContextBudget(None)), tmp_path / "pack"
    )
    rendered = result.content.read_text(encoding="utf-8")

    assert "`![inline](assets/example.png)`" in rendered
    assert "![fenced](assets/example.png)" in rendered
    assert "![real](sources/source-001/assets/example.png)" in rendered


def test_source_export_rejects_absolute_paths_in_processed_content(tmp_path: Path) -> None:
    source = tmp_path / "lesson.txt"
    source.write_text("original", encoding="utf-8")

    def processor(_source: Path, source_id: str, source_root: Path) -> Path:
        package = source_root / source_id
        package.mkdir(parents=True)
        (package / "content.md").write_text(
            "Private reference: C:\\Users\\Alice\\secret.png", encoding="utf-8"
        )
        (package / "manifest.json").write_text(
            json.dumps({"source": {"name": source.name}, "warnings": []}),
            encoding="utf-8",
        )
        return package

    with pytest.raises(ValueError, match="local absolute path"):
        create_context_pack(
            sources=(source,),
            output_root=tmp_path / "outputs",
            budget=ContextBudget(None),
            source_processor=processor,
        )

    assert list((tmp_path / "outputs").iterdir()) == []


def test_source_export_redacts_diagnostic_paths_with_explicit_warning(tmp_path: Path) -> None:
    source = tmp_path / "lesson.txt"
    source.write_text("original", encoding="utf-8")

    def processor(_source: Path, source_id: str, source_root: Path) -> Path:
        package = source_root / source_id
        package.mkdir(parents=True)
        (package / "content.md").write_text("Safe content.", encoding="utf-8")
        (package / "manifest.json").write_text(
            json.dumps(
                {
                    "source": {"name": source.name},
                    "warnings": [
                        {"code": "missing_image", "message": "C:\\Users\\Alice\\secret.png"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        return package

    result = create_context_pack(
        sources=(source,),
        output_root=tmp_path / "outputs",
        budget=ContextBudget(None),
        source_processor=processor,
    )
    report_text = result.context_report.read_text(encoding="utf-8")

    assert "C:\\Users\\Alice" not in report_text
    assert "[local path omitted]" in report_text
    assert "privacy_path_redacted" in report_text


def test_orchestrator_removes_only_its_new_output_after_source_processing_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "lesson.txt"
    source.write_text("original", encoding="utf-8")

    def broken_processor(_source: Path, _source_id: str, _source_root: Path) -> Path:
        raise RuntimeError("fixture failure")

    with pytest.raises(RuntimeError, match="fixture failure"):
        create_context_pack(
            sources=(source,),
            output_root=tmp_path / "outputs",
            budget=ContextBudget(None),
            source_processor=broken_processor,
        )

    assert source.read_text(encoding="utf-8") == "original"
    assert list((tmp_path / "outputs").iterdir()) == []
