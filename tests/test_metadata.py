from datetime import datetime
from pathlib import Path

from ai_material_preprocessor.services.metadata import (
    MediaMetadata,
    metadata_from_exiftool,
    metadata_from_ffprobe,
)


def test_exiftool_metadata_prefers_original_capture_time_and_named_location() -> None:
    payload = [{
        "DateTimeOriginal": "2026:07:31 15:30:21+08:00",
        "CreateDate": "2026:07:30 12:00:00",
        "GPSLatitude": 30.2512,
        "GPSLongitude": 120.1693,
        "City": "杭州",
        "Location": "西湖",
        "Duration": 12.5,
        "ImageWidth": 3840,
        "ImageHeight": 2160,
        "CompressorName": "HEVC",
        "Make": "Apple",
        "Model": "iPhone 15 Pro",
    }]

    result = metadata_from_exiftool(payload, Path("clip.mp4"))

    assert result.captured_at == datetime.fromisoformat("2026-07-31T15:30:21+08:00")
    assert result.latitude == 30.2512
    assert result.longitude == 120.1693
    assert result.location_label == "杭州-西湖"
    assert result.source == "ExifTool"
    assert result.duration_seconds == 12.5
    assert result.resolution == "3840x2160"
    assert result.codec == "HEVC"
    assert result.camera == "Apple-iPhone 15 Pro"


def test_ffprobe_parses_quicktime_iso6709_location() -> None:
    payload = {
        "format": {"tags": {
            "creation_time": "2026-07-31T07:30:21.000000Z",
            "com.apple.quicktime.location.ISO6709": "+30.2512+120.1693/",
        }},
        "duration": "8.25",
        "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}],
    }

    result = metadata_from_ffprobe(payload, Path("clip.mov"))

    assert result.captured_at == datetime.fromisoformat("2026-07-31T07:30:21+00:00")
    assert result.latitude == 30.2512
    assert result.longitude == 120.1693
    assert result.location_label == "30.2512_120.1693"
    assert result.source == "ffprobe"
    assert result.duration_seconds == 8.25
    assert result.resolution == "1920x1080"
    assert result.codec == "h264"


def test_empty_metadata_falls_back_to_file_time(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    expected = datetime.fromtimestamp(source.stat().st_mtime).astimezone()

    result = metadata_from_ffprobe({}, source)

    assert abs((result.captured_at - expected).total_seconds()) < 1
    assert result.location_label == ""


def test_media_metadata_display_uses_manual_location_override() -> None:
    metadata = MediaMetadata(
        captured_at=datetime(2026, 7, 31, 15, 30),
        latitude=30.2,
        longitude=120.1,
        location_label="坐标地点",
        source="test",
    )
    assert metadata.effective_location("杭州西湖") == "杭州西湖"
