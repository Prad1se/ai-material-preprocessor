from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ai_material_preprocessor.preview_models import (
    PreviewRisk,
    PreviewRiskLevel,
    SourceFilePreview,
    VideoPreview,
)
from ai_material_preprocessor.ui.preview_dialog import DocumentReportDialog, VideoPreviewDialog


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
        "risks": [{"code": "low_ocr_confidence", "level": "warning", "message": "OCR 需核对"}],
        "parameters": {"模式": "AI 增强", "目标长度": "4000 tokens"},
    }

    dialog = DocumentReportDialog([report], ["D:/output/content.md"])
    qtbot.addWidget(dialog)

    assert "# 课程" in dialog.markdown_preview.toPlainText()
    assert dialog.outline.topLevelItemCount() == 2
    assert dialog.chunk_table.rowCount() == 2
    assert dialog.ocr_table.rowCount() == 1
    assert "OCR 需核对" in dialog.risk_list.item(0).text()


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
