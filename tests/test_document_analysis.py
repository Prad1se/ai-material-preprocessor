from __future__ import annotations

from pathlib import Path

from ai_material_preprocessor.services.document_analysis import (
    EnhancementOptions,
    analyze_document,
)


def test_analysis_keeps_document_pipeline_cleaning_quality_and_splitting_behavior(
    tmp_path: Path,
) -> None:
    raw = "# 课程\n\n\n#### 跳级标题\n\n" + ("内容。" * 90)

    analysis = analyze_document(
        raw_markdown=raw,
        source_suffix=".pptx",
        base_dir=tmp_path,
        options=EnhancementOptions(target_tokens=40, max_tokens=60),
    )

    assert "\n\n\n" not in analysis.cleaned_markdown
    assert any(issue.code == "heading_jump" for issue in analysis.quality.issues)
    assert len(analysis.chunks) > 1


def test_analysis_deduplicates_and_optionally_appends_ocr_before_quality_and_splitting(
    tmp_path: Path,
) -> None:
    ocr_pages = (
        ("第 1 页", "课程资料\n第一页内容", 0.90),
        ("第 2 页", "课程资料\n第二页内容", 0.80),
        ("第 3 页", "课程资料\n第三页内容", 0.70),
    )

    analysis = analyze_document(
        raw_markdown="# 扫描件\n",
        source_suffix=".pdf",
        base_dir=tmp_path,
        options=EnhancementOptions(split_enabled=False, ocr_enabled=True),
        ocr_pages=ocr_pages,
        append_ocr_pages=True,
    )

    assert "课程资料" not in analysis.cleaned_markdown
    assert "第一页内容" in analysis.cleaned_markdown
    assert analysis.ocr_pages == (
        ("第 1 页", "第一页内容", 0.90),
        ("第 2 页", "第二页内容", 0.80),
        ("第 3 页", "第三页内容", 0.70),
    )
    assert analysis.chunks == ()
