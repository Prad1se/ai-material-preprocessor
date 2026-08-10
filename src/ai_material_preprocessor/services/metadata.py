from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from ..converters.common import run_command
from ..infrastructure.processes import CancellationToken

ISO6709 = re.compile(r"(?P<lat>[+-]\d+(?:\.\d+)?)(?P<lon>[+-]\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class MediaMetadata:
    captured_at: datetime
    latitude: float | None
    longitude: float | None
    location_label: str
    source: str
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    codec: str = ""
    make: str = ""
    model: str = ""
    frame_rate: float | None = None

    def effective_location(self, manual_override: str = "") -> str:
        return manual_override.strip() or self.location_label

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}" if self.width and self.height else ""

    @property
    def camera(self) -> str:
        return "-".join(value for value in (self.make, self.model) if value)


def _file_time(source: Path) -> datetime:
    return datetime.fromtimestamp(source.stat().st_mtime).astimezone()


def _parse_datetime(value: Any, source: Path) -> datetime:
    if not value:
        return _file_time(source)
    raw = str(value).strip()
    candidates = [
        raw.replace("Z", "+00:00"),
        raw.replace(":", "-", 2).replace(" ", "T", 1),
    ]
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return _file_time(source)


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _frame_rate(value: Any) -> float | None:
    if isinstance(value, str) and "/" in value:
        numerator, _, denominator = value.partition("/")
        try:
            divisor = float(denominator)
            return round(float(numerator) / divisor, 2) if divisor else None
        except ValueError:
            return None
    result = _number(value)
    return round(result, 2) if result is not None else None


def _coordinate_label(latitude: float | None, longitude: float | None) -> str:
    if latitude is None or longitude is None:
        return ""
    return f"{latitude:.4f}_{longitude:.4f}"


def metadata_from_exiftool(payload: list[dict[str, Any]], source: Path) -> MediaMetadata:
    values = payload[0] if payload else {}
    captured = _parse_datetime(
        values.get("DateTimeOriginal")
        or values.get("MediaCreateDate")
        or values.get("CreateDate")
        or values.get("TrackCreateDate"),
        source,
    )
    latitude = _number(values.get("GPSLatitude"))
    longitude = _number(values.get("GPSLongitude"))
    place_parts: list[str] = []
    for key in ("Country", "State", "City", "Location"):
        value = str(values.get(key, "")).strip()
        if value and value not in place_parts:
            place_parts.append(value)
    location = "-".join(place_parts) or _coordinate_label(latitude, longitude)
    return MediaMetadata(
        captured,
        latitude,
        longitude,
        location,
        "ExifTool",
        duration_seconds=_number(values.get("Duration")),
        width=int(_number(values.get("ImageWidth") or values.get("SourceImageWidth")) or 0) or None,
        height=int(_number(values.get("ImageHeight") or values.get("SourceImageHeight")) or 0)
        or None,
        codec=str(values.get("CompressorName") or values.get("VideoCodec") or "").strip(),
        make=str(values.get("Make") or values.get("DeviceManufacturer") or "").strip(),
        model=str(values.get("Model") or values.get("DeviceModelName") or "").strip(),
        frame_rate=_frame_rate(values.get("VideoFrameRate") or values.get("FrameRate")),
    )


def _flatten_ffprobe_tags(payload: dict[str, Any]) -> dict[str, str]:
    tags: dict[str, str] = {}
    for key, value in payload.get("format", {}).get("tags", {}).items():
        tags[str(key).lower()] = str(value)
    for stream in payload.get("streams", []):
        for key, value in stream.get("tags", {}).items():
            tags.setdefault(str(key).lower(), str(value))
    return tags


def metadata_from_ffprobe(payload: dict[str, Any], source: Path) -> MediaMetadata:
    tags = _flatten_ffprobe_tags(payload)
    captured = _parse_datetime(tags.get("creation_time") or tags.get("date"), source)
    raw_location = tags.get("com.apple.quicktime.location.iso6709") or tags.get("location") or ""
    match = ISO6709.search(raw_location)
    latitude = float(match.group("lat")) if match else None
    longitude = float(match.group("lon")) if match else None
    named_location = tags.get("com.apple.quicktime.location.name", "").strip()
    location = named_location or _coordinate_label(latitude, longitude)
    video: dict[str, Any] = next(
        (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"),
        {},
    )
    format_values = payload.get("format", {})
    return MediaMetadata(
        captured,
        latitude,
        longitude,
        location,
        "ffprobe",
        duration_seconds=_number(format_values.get("duration") or payload.get("duration")),
        width=int(_number(video.get("width")) or 0) or None,
        height=int(_number(video.get("height")) or 0) or None,
        codec=str(video.get("codec_name") or "").strip(),
        make=tags.get("make", "").strip(),
        model=(tags.get("model") or tags.get("com.apple.quicktime.model") or "").strip(),
        frame_rate=_frame_rate(video.get("avg_frame_rate") or video.get("r_frame_rate")),
    )


def read_media_metadata(
    source: Path,
    exiftool: str | None,
    ffprobe: str | None,
    *,
    ffmpeg: str | None = None,
    runner=run_command,
    cancellation: CancellationToken | None = None,
) -> MediaMetadata:
    if exiftool:
        try:
            result = runner(
                [
                    exiftool,
                    "-json",
                    "-n",
                    "-api",
                    "QuickTimeUTC=1",
                    "-DateTimeOriginal",
                    "-MediaCreateDate",
                    "-CreateDate",
                    "-TrackCreateDate",
                    "-GPSLatitude",
                    "-GPSLongitude",
                    "-Country",
                    "-State",
                    "-City",
                    "-Location",
                    "-Duration",
                    "-ImageWidth",
                    "-ImageHeight",
                    "-CompressorName",
                    "-VideoCodec",
                    "-VideoFrameRate",
                    "-FrameRate",
                    "-Make",
                    "-Model",
                    "-DeviceManufacturer",
                    "-DeviceModelName",
                    str(source),
                ],
                tool_name="ExifTool",
                cancellation=cancellation,
            )
            return metadata_from_exiftool(json.loads(result.stdout or "[]"), source)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            pass

    if ffprobe:
        try:
            result = runner(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_entries",
                    "format=duration:format_tags:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate:stream_tags",
                    str(source),
                ],
                tool_name="ffprobe",
                cancellation=cancellation,
            )
            return metadata_from_ffprobe(json.loads(result.stdout or "{}"), source)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            pass

    if ffmpeg:
        try:
            result = runner(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-i",
                    str(source),
                    "-f",
                    "ffmetadata",
                    "-",
                ],
                tool_name="FFmpeg",
                cancellation=cancellation,
            )
            tags: dict[str, str] = {}
            for raw_line in (result.stdout or "").splitlines():
                line = raw_line.strip()
                if not line or line.startswith((";", "#")) or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                tags[key.strip()] = value.strip()
            parsed = metadata_from_ffprobe({"format": {"tags": tags}}, source)
            return replace(parsed, source="FFmpeg")
        except (OSError, RuntimeError, ValueError):
            pass

    return MediaMetadata(_file_time(source), None, None, "", "文件时间")
