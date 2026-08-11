from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from ..errors import ErrorCode, UserFacingError
from ..infrastructure.processes import CancellationToken
from ..preview_models import PreviewRisk, PreviewRiskLevel, VideoPreview
from .files import safe_component, unique_path
from .metadata import MediaMetadata
from .naming import build_video_name


class OrganizationMode(StrEnum):
    DATE = "date"
    LOCATION = "location"
    DATE_LOCATION = "date_location"


@dataclass(frozen=True)
class VideoOrganizationPlan:
    source: Path
    output: Path
    mode: OrganizationMode
    location: str
    collision_avoided: bool


@dataclass(frozen=True)
class DuplicateVideoGroup:
    sha256: str
    duration_seconds: float
    resolution: str
    sources: tuple[Path, ...]


def _coordinate_key(latitude: float, longitude: float) -> str:
    return f"{latitude:.4f},{longitude:.4f}"


def resolve_local_location(
    metadata: MediaMetadata,
    dictionary: dict[str, str] | None = None,
    *,
    manual_override: str = "",
) -> str:
    if manual_override.strip():
        return manual_override.strip()
    coordinate_label = (
        f"{metadata.latitude:.4f}_{metadata.longitude:.4f}"
        if metadata.latitude is not None and metadata.longitude is not None
        else ""
    )
    if metadata.location_label and metadata.location_label != coordinate_label:
        return metadata.location_label
    if metadata.latitude is not None and metadata.longitude is not None:
        local = (dictionary or {}).get(_coordinate_key(metadata.latitude, metadata.longitude), "")
        if local.strip():
            return local.strip()
    return metadata.location_label


def plan_video_organization(
    source: Path,
    output_root: Path,
    metadata: MediaMetadata,
    mode: OrganizationMode,
    *,
    template: str,
    index: int,
    manual_location: str = "",
    project_name: str = "",
    location_dictionary: dict[str, str] | None = None,
) -> VideoOrganizationPlan:
    location = resolve_local_location(
        metadata,
        location_dictionary,
        manual_override=manual_location,
    )
    date_folder = metadata.captured_at.strftime("%Y-%m-%d")
    destination = output_root
    if mode in {OrganizationMode.DATE, OrganizationMode.DATE_LOCATION}:
        destination = destination / metadata.captured_at.strftime("%Y") / date_folder
    if mode in {OrganizationMode.LOCATION, OrganizationMode.DATE_LOCATION}:
        destination = destination / safe_component(location, "未知地点")
    intended = destination / build_video_name(
        source,
        metadata,
        template,
        index,
        location,
        project_name,
    )
    output = unique_path(intended)
    return VideoOrganizationPlan(source, output, mode, location, output != intended)


def copy_organized_video(
    plan: VideoOrganizationPlan,
    *,
    cancellation: CancellationToken | None = None,
) -> Path:
    if cancellation and cancellation.is_cancelled:
        raise UserFacingError(
            ErrorCode.CANCELLED,
            "任务已取消，原文件没有改动。",
            retryable=True,
        )
    plan.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(plan.source, plan.output)
        if cancellation and cancellation.is_cancelled:
            raise UserFacingError(
                ErrorCode.CANCELLED,
                "任务已取消，原文件没有改动。",
                retryable=True,
            )
    except Exception:
        if plan.output.exists():
            plan.output.unlink()
        raise
    return plan.output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_duplicate_videos(
    sources: list[Path],
    metadata: list[MediaMetadata],
) -> tuple[DuplicateVideoGroup, ...]:
    if len(sources) != len(metadata):
        raise ValueError("视频文件和元数据数量不一致。")
    grouped: dict[tuple[str, float, str], list[Path]] = {}
    for source, values in zip(sources, metadata, strict=True):
        key = (
            _sha256(source),
            round(float(values.duration_seconds or 0), 3),
            values.resolution,
        )
        grouped.setdefault(key, []).append(source)
    return tuple(
        DuplicateVideoGroup(sha256, duration, resolution, tuple(paths))
        for (sha256, duration, resolution), paths in grouped.items()
        if len(paths) > 1
    )


def annotate_duplicate_previews(
    previews: list[VideoPreview],
    groups: tuple[DuplicateVideoGroup, ...],
) -> tuple[VideoPreview, ...]:
    duplicates = {path.resolve() for group in groups for path in group.sources}
    return tuple(
        replace(
            preview,
            risks=preview.risks
            + (
                PreviewRisk(
                    "duplicate_material",
                    PreviewRiskLevel.WARNING,
                    "检测到内容、时长和分辨率相同的重复素材；请确认是否仍需处理。",
                ),
            ),
        )
        if preview.source.path.resolve() in duplicates
        else preview
        for preview in previews
    )
