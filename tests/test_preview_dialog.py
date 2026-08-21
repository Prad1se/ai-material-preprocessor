from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QTabWidget

from ai_material_preprocessor.preview_models import (
    PreviewRisk,
    PreviewRiskLevel,
    SourceFilePreview,
    VideoPreview,
)
from ai_material_preprocessor.services.source_map import (
    SourceLocation,
    SourceMap,
    SourceMapEntry,
    SourceMapSource,
)
from ai_material_preprocessor.ui.preview_dialog import DocumentReportDialog, VideoPreviewDialog


def _manual_source_map() -> SourceMap:
    location = SourceLocation(
        kind="page",
        label="第 37 页",
        display="PDF page 37",
        ordinal=37,
        confidence=None,
        fallback=False,
    )
    source = SourceMapSource(
        source_id="source-001",
        source_order=1,
        display_name="lecture.pdf",
        source_format=".pdf",
        provenance_level="page",
        sha256="a" * 64,
    )
    entry = SourceMapEntry(
        block_id="block-001",
        source_id="source-001",
        source_order=1,
        block_order=1,
        heading_context=("第一章",),
        estimated_tokens=1200,
        atomic=True,
        content="PDF paragraph.",
        content_sha256="b" * 64,
        content_verified=True,
        locations=(location,),
        primary_location=location,
    )
    return SourceMap(version=1, sources=(source,), entries=(entry,), integrity_ok=True)


def _context_report() -> dict[str, object]:
    return {
        "context_pack_version": 1,
        "source_count": 2,
        "pack_count": 3,
        "estimated_tokens": 64000,
        "requested_budget": 32000,
        "soft_target": 30000,
        "overflow_packs": 1,
        "integrity": "complete",
        "warnings": [{"message": "单个 Markdown 块超过预算，已保留完整内容。"}],
    }


def test_document_report_dialog_exposes_markdown_outline_chunks_and_ocr(qtbot) -> None:
    report = {
        "source": "课程.pptx",
        "score": 86,
        "estimated_tokens": 5200,
        "heading_count": 2,
        "image_count": 1,
        "cleaned_preview": "# 课程\n\n## 第一章\n\n正文",
        "headings": [
            {"level": 1, "title": "课程", "line": 1},
            {"level": 2, "title": "第一章", "line": 3},
        ],
        "chunks": [
            {"index": 1, "title": "第一章", "estimated_tokens": 3000},
            {"index": 2, "title": "第二章", "estimated_tokens": 2200},
        ],
        "ocr_pages": [{"label": "第 2 页", "confidence": 0.61, "low_confidence": True}],
        "risks": [
            {
                "code": "low_ocr_confidence",
                "level": "warning",
                "message": "OCR 需核对",
                "line": 8,
                "source_label": "幻灯片 2",
            }
        ],
        "parameters": {"模式": "AI 增强", "目标长度": "4000 tokens"},
    }

    dialog = DocumentReportDialog([report], ["D:/output/content.md"])
    qtbot.addWidget(dialog)

    assert "# 课程" in dialog.markdown_preview.toPlainText()
    assert dialog.outline.topLevelItemCount() == 2
    assert dialog.chunk_table.rowCount() == 2
    assert dialog.ocr_table.rowCount() == 1
    assert "OCR 需核对" in dialog.risk_list.item(0).text()
    assert "幻灯片 2 · 第 8 行" in dialog.risk_list.item(0).text()


def test_video_preview_dialog_shows_media_fields_estimate_and_risks(qtbot, tmp_path: Path) -> None:
    source = SourceFilePreview(
        tmp_path / "clip.mp4",
        "clip.mp4",
        ".mp4",
        1000,
        datetime(2026, 8, 10),
    )
    preview = VideoPreview(
        source=source,
        captured_at=datetime(2026, 8, 9, 12, 30),
        location="杭州西湖",
        duration_seconds=65.0,
        resolution="1920x1080",
        codec="h264",
        camera="Apple-iPhone",
        frame_rate=29.97,
        output_name="clip_compressed.mp4",
        estimated_size_min=400,
        estimated_size_max=800,
        risks=(PreviewRisk("lossy_video", PreviewRiskLevel.WARNING, "可能损失画质"),),
        parameters=(("CRF", "23"),),
    )

    dialog = VideoPreviewDialog([preview])
    qtbot.addWidget(dialog)

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 3).text() == "1920x1080"
    assert dialog.table.item(0, 4).text() == "29.97 fps"
    assert dialog.table.item(0, 7).text() == "clip_compressed.mp4"
    assert "可能损失画质" in dialog.risk_list.item(0).text()
    assert dialog.table.horizontalHeaderItem(9).text() == "GPS"
    assert dialog.table.horizontalHeaderItem(10).text() == "设备"


def test_document_report_dialog_renders_context_pack_summary(qtbot) -> None:
    dialog = DocumentReportDialog([_context_report()], ["D:/output/Context-Pack"])
    qtbot.addWidget(dialog)

    assert "3 个包" in dialog.context_pack_summary.text()
    assert "2 个来源" in dialog.context_pack_summary.text()
    assert "完整性 complete" in dialog.context_pack_summary.text()
    assert "超过预算" in dialog.warning_list.item(0).text()


def test_document_report_dialog_embeds_source_map_tab(qtbot) -> None:
    dialog = DocumentReportDialog(
        [_context_report()], ["D:/output/Context-Pack"], source_map=_manual_source_map()
    )
    qtbot.addWidget(dialog)

    assert "Source Map" in dialog.windowTitle()
    tabs = dialog.findChild(QTabWidget)
    assert tabs is not None
    assert "Source Map" in [tabs.tabText(index) for index in range(tabs.count())]
    assert dialog.source_map_view.blocks_table.rowCount() == 1
    assert dialog.source_map_view.card_file_value.text() == "lecture.pdf"
    assert dialog.source_map_view.card_location_value.text() == "PDF page 37"
    assert not dialog.source_map_view.back_button.isVisibleTo(dialog)


def test_document_report_dialog_source_map_tab_shows_fallback_and_confidence(
    qtbot,
) -> None:
    fallback = SourceLocation(
        kind="document",
        label="Word 文档",
        display="Document-level fallback",
        ordinal=None,
        confidence=None,
        fallback=True,
    )
    ocr = SourceLocation(
        kind="ocr",
        label="第 2 页",
        display="OCR 第 2 页 (65% confidence)",
        ordinal=None,
        confidence=0.65,
        fallback=False,
    )
    source = SourceMapSource(
        source_id="source-001",
        source_order=1,
        display_name="scan.pdf",
        source_format=".pdf",
        provenance_level="ocr",
        sha256=None,
    )
    entry = SourceMapEntry(
        block_id="block-001",
        source_id="source-001",
        source_order=1,
        block_order=1,
        heading_context=(),
        estimated_tokens=800,
        atomic=True,
        content="OCR text.",
        content_sha256="c" * 64,
        content_verified=True,
        locations=(ocr, fallback),
        primary_location=ocr,
    )
    source_map = SourceMap(version=1, sources=(source,), entries=(entry,), integrity_ok=True)

    dialog = DocumentReportDialog(
        [_context_report()], ["D:/output/Context-Pack"], source_map=source_map
    )
    qtbot.addWidget(dialog)

    assert dialog.source_map_view.card_location_value.text() == "OCR 第 2 页 (65% confidence)"
    assert not dialog.source_map_view.card_fallback_note.isVisibleTo(dialog)


def test_document_report_dialog_source_map_tab_degraded_pack_shows_notice(
    qtbot,
) -> None:
    source_map = _manual_source_map()
    degraded = SourceMap(
        version=1,
        sources=source_map.sources,
        entries=source_map.entries,
        integrity_ok=False,
    )

    dialog = DocumentReportDialog(
        [_context_report()], ["D:/output/Context-Pack"], source_map=degraded
    )
    qtbot.addWidget(dialog)

    assert dialog.source_map_view.integrity_notice.isVisibleTo(dialog)
