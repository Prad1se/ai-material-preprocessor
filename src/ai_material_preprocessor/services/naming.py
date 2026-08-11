from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .files import safe_component, unique_path
from .metadata import MediaMetadata


@dataclass(frozen=True)
class RenamePreview:
    source: Path
    output: Path
    metadata: MediaMetadata
    collision_avoided: bool


def build_video_name(
    source: Path,
    metadata: MediaMetadata,
    template: str,
    index: int,
    manual_location: str = "",
    project_name: str = "",
) -> str:
    captured = metadata.captured_at
    duration = round(metadata.duration_seconds or 0)
    values = {
        "date": f"{captured:%Y-%m-%d}",
        "time": f"{captured:%H%M%S}",
        "location": safe_component(metadata.effective_location(manual_location), ""),
        "index": f"{index:03d}",
        "original": safe_component(source.stem, "video"),
        "year": f"{captured:%Y}",
        "month": f"{captured:%m}",
        "day": f"{captured:%d}",
        "hour": f"{captured:%H}",
        "minute": f"{captured:%M}",
        "second": f"{captured:%S}",
        "datetime": f"{captured:%Y-%m-%d_%H%M%S}",
        "latitude": (
            f"{abs(metadata.latitude):.4f}{'N' if metadata.latitude >= 0 else 'S'}"
            if metadata.latitude is not None
            else ""
        ),
        "longitude": (
            f"{abs(metadata.longitude):.4f}{'E' if metadata.longitude >= 0 else 'W'}"
            if metadata.longitude is not None
            else ""
        ),
        "resolution": metadata.resolution,
        "width": str(metadata.width or ""),
        "height": str(metadata.height or ""),
        "duration_s": str(duration) if metadata.duration_seconds is not None else "",
        "codec": safe_component(metadata.codec, ""),
        "camera": safe_component(metadata.camera, ""),
        "make": safe_component(metadata.make, ""),
        "model": safe_component(metadata.model, ""),
        "metadata_source": safe_component(metadata.source, ""),
        "device": safe_component(metadata.camera, ""),
        "project": safe_component(project_name, ""),
    }
    try:
        stem = template.format(**values)
    except KeyError as exc:
        raise ValueError(f"未知命名字段：{exc.args[0]}") from exc
    stem = re.sub(r"[_\- ]{2,}", "_", stem).strip(" ._-")
    return f"{safe_component(stem, 'video')}{source.suffix.lower()}"


def preview_video_rename(
    source: Path,
    destination: Path,
    metadata: MediaMetadata,
    template: str,
    index: int,
    manual_location: str = "",
    project_name: str = "",
) -> RenamePreview:
    intended = destination / build_video_name(
        source,
        metadata,
        template,
        index,
        manual_location,
        project_name,
    )
    output = unique_path(intended)
    return RenamePreview(source, output, metadata, output != intended)
