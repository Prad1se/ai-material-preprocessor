from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ai_material_preprocessor.models import Operation
from ai_material_preprocessor.services.document_enhancement import EnhancementOptions
from ai_material_preprocessor.services.metadata import MediaMetadata
from ai_material_preprocessor.services.preview import (
    build_batch_rename_preview,
    build_document_preview,
    build_video_preview,
    completed_contact_sheet,
)


def test_document_preview_reports_structure_chunks_ocr_and_content_risks(tmp_path: Path) -> None:
    source = tmp_path / "lesson.pptx"
    source.write_bytes(b"presentation")
    raw = """# 课程

#### 跳级标题

| 项目 | 内容 |
| --- | --- |
| 公式 | \\(x+y\\) |

```python
print('ok')
```

![缺失图片](assets/missing.png)

""" + ("较长内容。" * 80)

    preview = build_document_preview(
        source,
        raw,
        base_dir=tmp_path,
        options=EnhancementOptions(target_tokens=40, max_tokens=60, ocr_enabled=True),
        ocr_pages=(("第 1 页", "识别内容", 0.62), ("第 2 页", "清晰内容", 0.96)),
        parameters={"模式": "AI 增强", "目标长度": "40 tokens"},
    )

    assert preview.source.name == "lesson.pptx"
    assert preview.source.size_bytes == len(b"presentation")
    assert [item.level for item in preview.headings] == [1, 2]
    assert preview.cleaned_markdown.startswith("# 课程")
    assert len(preview.chunks) > 1
    assert preview.ocr_pages[0].low_confidence is True
    assert preview.ocr_pages[1].low_confidence is False
    codes = {risk.code for risk in preview.risks}
    assert {"table_layout", "formula", "code_block", "missing_image", "low_ocr_confidence"} <= codes
    assert dict(preview.parameters)["模式"] == "AI 增强"


def video_metadata(location: str = "杭州西湖") -> MediaMetadata:
    return MediaMetadata(
        captured_at=datetime(2026, 7, 31, 15, 30, 21),
        latitude=30.2512,
        longitude=120.1693,
        location_label=location,
        source="fixture",
        duration_seconds=120.0,
        width=3840,
        height=2160,
        codec="hevc",
        make="Apple",
        model="iPhone 15 Pro",
        frame_rate=29.97,
    )


def test_video_preview_exposes_metadata_output_estimate_and_loss_risk(tmp_path: Path) -> None:
    source = tmp_path / "旅行 视频.mov"
    source.write_bytes(b"x" * 10_000)

    preview = build_video_preview(
        source,
        video_metadata(),
        Operation.COMPRESS_VIDEO,
        tmp_path / "out",
        parameters={"compression_crf": 23, "compression_preset": "medium"},
    )

    assert preview.resolution == "3840x2160"
    assert preview.duration_seconds == 120.0
    assert preview.codec == "hevc"
    assert preview.frame_rate == 29.97
    assert preview.output_name == "旅行 视频_compressed.mp4"
    assert 0 < preview.estimated_size_min <= preview.estimated_size_max
    assert {risk.code for risk in preview.risks} >= {"lossy_video", "codec_change"}
    assert not (tmp_path / "out").exists()


def test_batch_rename_preview_is_a_dry_run_and_marks_planned_collisions(tmp_path: Path) -> None:
    sources = [tmp_path / "a.mov", tmp_path / "b.mov"]
    for source in sources:
        source.write_bytes(b"source")

    previews = build_batch_rename_preview(
        sources,
        [video_metadata(), video_metadata()],
        tmp_path / "out",
        template="{date}_{location}",
    )

    assert len(previews) == 2
    assert previews[0].output_name == "2026-07-31_杭州西湖.mov"
    assert previews[1].output_name == "2026-07-31_杭州西湖_2.mov"
    assert any(risk.code == "planned_name_collision" for risk in previews[1].risks)
    assert not (tmp_path / "out").exists()
    assert all(source.read_bytes() == b"source" for source in sources)


def test_completed_contact_sheet_only_accepts_an_existing_storyboard_image(tmp_path: Path) -> None:
    package = tmp_path / "clip_关键帧包"
    package.mkdir()
    sheet = package / "contact-sheet.jpg"
    sheet.write_bytes(b"jpeg")

    assert completed_contact_sheet(sheet) == sheet
    assert completed_contact_sheet(package / "missing.jpg") is None
    assert completed_contact_sheet(tmp_path / "ordinary.mp4") is None
