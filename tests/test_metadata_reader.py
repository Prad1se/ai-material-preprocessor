import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from ai_material_preprocessor.services.metadata import read_media_metadata


def test_reader_prefers_exiftool(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    calls: list[list[str]] = []

    def runner(command: list[str]):
        calls.append(command)
        return SimpleNamespace(stdout=json.dumps([{
            "DateTimeOriginal": "2026:07:31 15:30:21+08:00",
            "GPSLatitude": 30.2,
            "GPSLongitude": 120.1,
        }]))

    result = read_media_metadata(source, "exiftool.exe", "ffprobe.exe", runner=runner)

    assert result.source == "ExifTool"
    assert len(calls) == 1
    assert calls[0][0] == "exiftool.exe"
    assert "-json" in calls[0]
    assert "-n" in calls[0]


def test_reader_falls_back_to_ffprobe_when_exiftool_fails(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")

    def runner(command: list[str]):
        if command[0] == "exiftool.exe":
            raise RuntimeError("bad metadata")
        return SimpleNamespace(stdout=json.dumps({
            "format": {"tags": {"creation_time": "2026-07-31T01:02:03Z"}},
            "streams": [],
        }))

    result = read_media_metadata(source, "exiftool.exe", "ffprobe.exe", runner=runner)

    assert result.source == "ffprobe"
    assert result.captured_at == datetime.fromisoformat("2026-07-31T01:02:03+00:00")


def test_reader_uses_file_time_without_metadata_tools(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    result = read_media_metadata(source, None, None)
    assert result.source == "文件时间"


def test_reader_uses_ffmpeg_ffmetadata_when_ffprobe_is_missing(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")

    def runner(command: list[str]):
        assert command[0] == "ffmpeg.exe"
        return SimpleNamespace(stdout=(
            ";FFMETADATA1\n"
            "creation_time=2026-07-31T01:02:03Z\n"
            "location=+30.2512+120.1693/\n"
        ))

    result = read_media_metadata(
        source, None, None, ffmpeg="ffmpeg.exe", runner=runner
    )

    assert result.source == "FFmpeg"
    assert result.location_label == "30.2512_120.1693"
