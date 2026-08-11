from __future__ import annotations

from pathlib import Path

from ai_material_preprocessor.models import Job, Operation, ToolStatus
from ai_material_preprocessor.services import video_service
from ai_material_preprocessor.services.video_service import VideoProcessingService


def test_video_service_routes_organization_with_project_and_local_dictionary(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "旅行.mov"
    source.write_bytes(b"video")
    expected = tmp_path / "library" / "2026" / "organized.mov"
    captured: dict[str, object] = {}

    def fake_organize(*args, **kwargs) -> Path:
        captured["args"] = args
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(video_service, "organize_copy", fake_organize)
    service = VideoProcessingService(
        {
            "ffprobe": ToolStatus("ffprobe", "D:/tools/ffprobe.exe"),
            "exiftool": ToolStatus("exiftool", "D:/tools/exiftool.exe"),
        },
        {
            "video": {
                "compression_crf": 23,
                "compression_preset": "medium",
                "audio_format": "mp3",
                "audio_bitrate": "192k",
                "scene_threshold": 0.3,
                "max_keyframes": 24,
                "contact_sheet_columns": 4,
                "rename_template": "{date}_{project}_{index}",
                "project_name": "默认项目",
                "organize_mode": "date_location",
                "location_dictionary": {"30.2512,120.1693": "杭州西湖"},
            }
        },
    )

    result = service.convert(
        Job(
            source,
            Operation.ORGANIZE_VIDEO,
            tmp_path / "library",
            location="手动地点",
            project="毕业短片",
        ),
        3,
    )

    assert result == expected
    assert captured["project_name"] == "毕业短片"
    assert captured["organize_mode"] == "date_location"
    assert captured["location_dictionary"] == {"30.2512,120.1693": "杭州西湖"}
