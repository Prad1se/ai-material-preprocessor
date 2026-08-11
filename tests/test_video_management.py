from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ai_material_preprocessor.services.metadata import MediaMetadata, metadata_from_exiftool
from ai_material_preprocessor.services.naming import build_video_name
from ai_material_preprocessor.services.video_management import (
    OrganizationMode,
    copy_organized_video,
    find_duplicate_videos,
    plan_video_organization,
    resolve_local_location,
)


def metadata(*, location: str = "", duration: float = 12.5) -> MediaMetadata:
    return MediaMetadata(
        captured_at=datetime(2026, 7, 31, 15, 30, 21),
        latitude=30.2512,
        longitude=120.1693,
        location_label=location,
        source="fixture",
        duration_seconds=duration,
        width=1920,
        height=1080,
        codec="h264",
        make="Apple",
        model="iPhone 15 Pro",
    )


def test_exiftool_records_capture_time_priority_source() -> None:
    result = metadata_from_exiftool(
        [
            {
                "DateTimeOriginal": "2026:07:31 15:30:21+08:00",
                "MediaCreateDate": "2026:07:30 12:00:00+08:00",
            }
        ],
        Path("clip.mov"),
    )

    assert result.capture_time_source == "DateTimeOriginal"
    assert result.captured_at == datetime.fromisoformat("2026-07-31T15:30:21+08:00")


def test_local_location_dictionary_is_offline_and_manual_value_wins() -> None:
    dictionary = {"30.2512,120.1693": "杭州西湖"}

    assert resolve_local_location(metadata(), dictionary) == "杭州西湖"
    assert resolve_local_location(metadata(), dictionary, manual_override="西湖边") == "西湖边"
    assert resolve_local_location(metadata(location="相机地点"), dictionary) == "相机地点"


def test_project_name_is_available_to_video_naming_template() -> None:
    name = build_video_name(
        Path("VID_0001.MOV"),
        metadata(location="杭州西湖"),
        "{date}_{location}_{project}_{device}_{index}",
        2,
        project_name="毕业短片",
    )

    assert name == "2026-07-31_杭州西湖_毕业短片_Apple-iPhone-15-Pro_002.mov"


def test_organization_plan_is_dry_run_then_copies_without_touching_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "VID_0001.mov"
    source.write_bytes(b"original")
    output = tmp_path / "library"

    plan = plan_video_organization(
        source,
        output,
        metadata(location="杭州西湖"),
        OrganizationMode.DATE_LOCATION,
        template="{date}_{project}_{index}",
        index=1,
        project_name="旅行",
    )

    assert plan.output == output / "2026" / "2026-07-31" / "杭州西湖" / "2026-07-31_旅行_001.mov"
    assert not output.exists()

    created = copy_organized_video(plan)

    assert created.read_bytes() == b"original"
    assert source.read_bytes() == b"original"


def test_duplicate_detection_combines_hash_duration_and_resolution(tmp_path: Path) -> None:
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    different = tmp_path / "c.mp4"
    first.write_bytes(b"same-video")
    second.write_bytes(b"same-video")
    different.write_bytes(b"different")

    groups = find_duplicate_videos(
        [first, second, different],
        [metadata(), metadata(), metadata()],
    )

    assert len(groups) == 1
    assert groups[0].sources == (first, second)
    assert len(groups[0].sha256) == 64
    assert groups[0].duration_seconds == 12.5
    assert groups[0].resolution == "1920x1080"
