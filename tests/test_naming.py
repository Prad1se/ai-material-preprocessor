from datetime import datetime
from pathlib import Path

from ai_material_preprocessor.services.metadata import MediaMetadata
from ai_material_preprocessor.services.naming import build_video_name, preview_video_rename


def metadata(location: str = "杭州西湖") -> MediaMetadata:
    return MediaMetadata(
        datetime(2026, 7, 31, 15, 30, 21),
        30.2512,
        120.1693,
        location,
        "test",
        duration_seconds=65.4,
        width=1920,
        height=1080,
        codec="h264",
        make="Apple",
        model="iPhone 15 Pro",
    )


def test_template_builds_safe_predictable_name() -> None:
    result = build_video_name(
        source=Path("VID_0001.MOV"),
        metadata=metadata("杭州:西湖"),
        template="{date}_{time}_{location}_{index}",
        index=3,
    )
    assert result == "2026-07-31_153021_杭州_西湖_003.mov"


def test_empty_location_does_not_leave_double_separator() -> None:
    result = build_video_name(Path("VID_0001.mp4"), metadata(""), "{date}_{location}_{index}", 1)
    assert result == "2026-07-31_001.mp4"


def test_preview_reports_collision_without_touching_disk(tmp_path: Path) -> None:
    source = tmp_path / "VID_0001.mp4"
    source.write_bytes(b"original")
    destination = tmp_path / "out"
    destination.mkdir()
    existing = destination / "2026-07-31_153021_杭州西湖_001.mp4"
    existing.write_bytes(b"existing")

    preview = preview_video_rename(
        source, destination, metadata(), "{date}_{time}_{location}_{index}", 1
    )

    assert preview.output.name == "2026-07-31_153021_杭州西湖_001_2.mp4"
    assert preview.collision_avoided is True
    assert source.read_bytes() == b"original"
    assert existing.read_bytes() == b"existing"


def test_rich_template_supports_calendar_media_camera_and_coordinate_fields() -> None:
    result = build_video_name(
        Path("VID_0001.MOV"),
        metadata(),
        "{year}{month}{day}_{hour}{minute}_{resolution}_{duration_s}s_{codec}_{camera}_{latitude}_{longitude}",
        1,
    )
    assert result == "20260731_1530_1920x1080_65s_h264_Apple-iPhone-15-Pro_30.2512N_120.1693E.mov"


def test_unknown_rich_field_still_has_actionable_error() -> None:
    try:
        build_video_name(Path("clip.mp4"), metadata(), "{not_a_field}", 1)
    except ValueError as exc:
        assert "not_a_field" in str(exc)
    else:
        raise AssertionError("unknown field should fail")
