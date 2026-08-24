from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..converters.common import run_command
from ..converters.video import (
    KeyframeArtifacts,
    create_proxy,
    extract_audio,
    generate_keyframe_artifacts,
)
from ..errors import ErrorCode, UserFacingError
from ..infrastructure.processes import CancellationToken
from ..models import Job, Operation, ToolStatus
from .files import unique_path
from .metadata import MediaMetadata, read_media_metadata
from .observability import DiagnosticLogger

VIDEO_AI_PACK_VERSION = 1


@dataclass(frozen=True)
class VideoPackSource:
    source_id: str
    display_name: str
    path: Path
    metadata: MediaMetadata
    source_sha256: str


@dataclass(frozen=True)
class VideoFrame:
    source_id: str
    frame_id: str
    path: str
    timestamp_seconds: float | None


@dataclass(frozen=True)
class VideoTimelineEntry:
    source_id: str
    frame_id: str
    timestamp_seconds: float | None
    timestamp_label: str | None
    frame: str


@dataclass(frozen=True)
class VideoPackWarning:
    code: str
    message: str
    source_id: str | None = None


@dataclass(frozen=True)
class VideoPackIntegrity:
    source_count: int
    declared_artifacts: int
    existing_artifacts: int
    missing_artifacts: tuple[str, ...]
    duplicate_ids: tuple[str, ...]
    duplicate_artifacts: tuple[str, ...]
    undeclared_core_artifacts: tuple[str, ...]
    path_violations: tuple[str, ...]
    source_order_preserved: bool
    timeline_order_preserved: bool
    status_consistent: bool
    source_hashes_unchanged: bool
    ok: bool


@dataclass(frozen=True)
class VideoAIPackPlan:
    sources: tuple[Path, ...]
    output_root: Path
    include_audio: bool
    include_proxy: bool
    proxy_crf: int
    scene_threshold: float
    max_keyframes: int
    contact_sheet_columns: int


@dataclass(frozen=True)
class VideoAIPackResult:
    output: Path
    report: dict[str, Any]


MetadataReader = Callable[..., MediaMetadata]
KeyframeGenerator = Callable[..., KeyframeArtifacts]
ArtifactGenerator = Callable[..., Path]
AudioProbe = Callable[..., bool | None]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _raise_if_cancelled(cancellation: CancellationToken | None) -> None:
    if cancellation and cancellation.is_cancelled:
        raise UserFacingError(
            ErrorCode.CANCELLED,
            "任务已取消，原文件没有改动。",
            retryable=True,
        )


def _sha256(path: Path, cancellation: CancellationToken | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            _raise_if_cancelled(cancellation)
            digest.update(block)
    return digest.hexdigest()


def _timestamp_label(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    total_milliseconds = round(max(0.0, seconds) * 1000)
    total_seconds, milliseconds = divmod(total_milliseconds, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds_value = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_value:02d}.{milliseconds:03d}"


def _relative(root: Path, path: Path) -> str:
    root_resolved = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise UserFacingError(
            ErrorCode.INTEGRITY_FAILED,
            "资料包路径验证失败，未发布不完整结果。",
        )
    return resolved.relative_to(root_resolved).as_posix()


def _confined_generated_file(package_root: Path, expected_dir: Path, path: Path) -> Path:
    package_resolved = package_root.resolve()
    expected_resolved = expected_dir.resolve()
    resolved = path.resolve()
    if (
        not expected_resolved.is_relative_to(package_resolved)
        or not resolved.is_relative_to(expected_resolved)
        or not resolved.is_file()
    ):
        raise UserFacingError(
            ErrorCode.INTEGRITY_FAILED,
            "资料包生成器返回了不安全的输出路径，未发布结果。",
        )
    return resolved


def _raise_if_fatal_optional_failure(
    exc: Exception,
    cancellation: CancellationToken | None,
) -> None:
    if isinstance(exc, UserFacingError) and exc.code in {
        ErrorCode.CANCELLED,
        ErrorCode.INTEGRITY_FAILED,
    }:
        raise exc
    _raise_if_cancelled(cancellation)


def probe_audio_stream(
    source: Path,
    ffprobe: str | None,
    *,
    runner=run_command,
    cancellation: CancellationToken | None = None,
) -> bool | None:
    if not ffprobe:
        return None
    result = runner(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(source),
        ],
        tool_name="ffprobe",
        cancellation=cancellation,
    )
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams", []) if isinstance(payload, dict) else []
    return any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in streams
    )


def validate_video_ai_pack(
    root: Path,
    *,
    source_ids: Iterable[str],
    frames: Iterable[VideoFrame],
    timeline: Iterable[VideoTimelineEntry],
    artifacts: Iterable[str],
    statuses: Iterable[dict[str, object]],
    source_hashes_unchanged: bool,
) -> VideoPackIntegrity:
    source_id_list = list(source_ids)
    frame_list = list(frames)
    timeline_list = list(timeline)
    artifact_list = list(artifacts)
    duplicate_ids = sorted(
        {
            value
            for value in [*source_id_list, *(frame.frame_id for frame in frame_list)]
            if [*source_id_list, *(frame.frame_id for frame in frame_list)].count(value) > 1
        }
    )
    duplicate_artifacts = sorted({path for path in artifact_list if artifact_list.count(path) > 1})
    path_violations: list[str] = []
    missing: list[str] = []
    root_resolved = root.resolve()
    for relative in artifact_list:
        candidate = Path(relative)
        resolved = (root / candidate).resolve()
        if candidate.is_absolute() or not resolved.is_relative_to(root_resolved):
            path_violations.append(relative)
        elif not resolved.is_file():
            missing.append(relative)
    declared = set(artifact_list)
    existing_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    undeclared = sorted(existing_files - declared)
    timeline_frame_ids = [entry.frame_id for entry in timeline_list]
    observed_source_order = list(dict.fromkeys(frame.source_id for frame in frame_list))
    source_order_preserved = observed_source_order == source_id_list
    timeline_order_preserved = len(timeline_list) == len(frame_list) and all(
        (
            entry.source_id,
            entry.frame_id,
            entry.frame,
            entry.timestamp_seconds,
        )
        == (
            frame.source_id,
            frame.frame_id,
            frame.path,
            frame.timestamp_seconds,
        )
        for entry, frame in zip(timeline_list, frame_list, strict=True)
    )
    timeline_order_preserved &= len(timeline_frame_ids) == len(set(timeline_frame_ids))
    status_consistent = True
    status_list = list(statuses)
    expected_statuses = {
        (source_id, artifact_type)
        for source_id in source_id_list
        for artifact_type in ("audio", "proxy")
    }
    actual_statuses = {
        (str(status.get("source_id") or ""), str(status.get("artifact_type") or ""))
        for status in status_list
    }
    status_consistent &= len(status_list) == len(expected_statuses)
    status_consistent &= actual_statuses == expected_statuses
    for status in status_list:
        requested = bool(status.get("requested"))
        state = str(status.get("status") or "")
        path = status.get("path")
        if state == "generated":
            status_consistent &= requested and isinstance(path, str) and path in declared
        elif state == "not_requested":
            status_consistent &= not requested and path is None
        elif state in {"unavailable", "failed"}:
            status_consistent &= requested and path is None
        else:
            status_consistent = False
    ok = not any(
        (
            duplicate_ids,
            duplicate_artifacts,
            path_violations,
            missing,
            undeclared,
        )
    ) and all(
        (
            source_order_preserved,
            timeline_order_preserved,
            status_consistent,
            source_hashes_unchanged,
        )
    )
    return VideoPackIntegrity(
        source_count=len(source_id_list),
        declared_artifacts=len(artifact_list),
        existing_artifacts=len(existing_files & declared),
        missing_artifacts=tuple(sorted(missing)),
        duplicate_ids=tuple(duplicate_ids),
        duplicate_artifacts=tuple(duplicate_artifacts),
        undeclared_core_artifacts=tuple(undeclared),
        path_violations=tuple(sorted(path_violations)),
        source_order_preserved=source_order_preserved,
        timeline_order_preserved=timeline_order_preserved,
        status_consistent=bool(status_consistent),
        source_hashes_unchanged=source_hashes_unchanged,
        ok=bool(ok),
    )


def validate_written_video_ai_pack_manifest(
    root: Path,
    *,
    source_ids: Iterable[str],
    frames: Iterable[VideoFrame],
    artifact_paths: Iterable[str],
) -> None:
    expected_source_ids = list(source_ids)
    expected_artifact_paths = list(artifact_paths)
    expected_frames = [
        (frame.source_id, frame.frame_id, frame.path, frame.timestamp_seconds) for frame in frames
    ]
    try:
        payload = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("manifest root must be an object")
        if payload.get("package_type") != "video_ai_pack":
            raise ValueError("invalid package type")
        if payload.get("video_ai_pack_version") != VIDEO_AI_PACK_VERSION:
            raise ValueError("invalid package version")
        if payload.get("source_count") != len(expected_source_ids):
            raise ValueError("source count mismatch")
        raw_sources = payload.get("sources")
        raw_artifacts = payload.get("artifacts")
        if not isinstance(raw_sources, list) or not isinstance(raw_artifacts, list):
            raise TypeError("invalid manifest collections")
        if [item.get("source_id") for item in raw_sources if isinstance(item, dict)] != (
            expected_source_ids
        ):
            raise ValueError("source order mismatch")
        actual_artifacts = [
            str(item.get("path")) for item in raw_artifacts if isinstance(item, dict)
        ]
        if actual_artifacts != expected_artifact_paths:
            raise ValueError("artifact declarations mismatch")
        actual_frames: list[tuple[object, object, object, object]] = []
        referenced_paths = [str(payload.get("timeline") or ""), *actual_artifacts]
        for source in raw_sources:
            if not isinstance(source, dict):
                raise TypeError("invalid source record")
            source_id = source.get("source_id")
            referenced_paths.extend(
                (str(source.get("metadata") or ""), str(source.get("contact_sheet") or ""))
            )
            source_frames = source.get("frames")
            if not isinstance(source_frames, list):
                raise TypeError("invalid source frames")
            for frame in source_frames:
                if not isinstance(frame, dict):
                    raise TypeError("invalid frame record")
                path = frame.get("path")
                referenced_paths.append(str(path or ""))
                actual_frames.append(
                    (source_id, frame.get("frame_id"), path, frame.get("timestamp_seconds"))
                )
            for artifact_type in ("audio", "proxy"):
                status = source.get(artifact_type)
                if not isinstance(status, dict):
                    raise TypeError("invalid artifact status")
                if status.get("status") == "generated":
                    referenced_paths.append(str(status.get("path") or ""))
        if actual_frames != expected_frames:
            raise ValueError("frame declarations mismatch")
        timeline_relative = str(payload.get("timeline") or "")
        timeline_path = (root / timeline_relative).resolve()
        if (
            not timeline_relative
            or Path(timeline_relative).is_absolute()
            or not timeline_path.is_relative_to(root.resolve())
            or not timeline_path.is_file()
        ):
            raise ValueError("invalid timeline reference")
        timeline_payload = json.loads(timeline_path.read_text(encoding="utf-8"))
        timeline_entries = (
            timeline_payload.get("entries") if isinstance(timeline_payload, dict) else None
        )
        if not isinstance(timeline_entries, list):
            raise TypeError("invalid timeline entries")
        actual_timeline: list[tuple[object, object, object, object]] = []
        for entry in timeline_entries:
            if not isinstance(entry, dict):
                raise TypeError("invalid timeline entry")
            actual_timeline.append(
                (
                    entry.get("source_id"),
                    entry.get("frame_id"),
                    entry.get("frame"),
                    entry.get("timestamp_seconds"),
                )
            )
        if actual_timeline != expected_frames:
            raise ValueError("timeline declarations mismatch")
        for relative in referenced_paths:
            if not relative:
                raise ValueError("empty manifest reference")
            candidate = (root / relative).resolve()
            if Path(relative).is_absolute() or not candidate.is_relative_to(root.resolve()):
                raise ValueError("manifest path escaped package")
            if not candidate.is_file():
                raise FileNotFoundError(relative)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise UserFacingError(
            ErrorCode.INTEGRITY_FAILED,
            "视频 AI 资料包 manifest 验证未通过，未发布结果。",
            technical_detail=f"{type(exc).__name__}: {exc}",
        ) from exc


class VideoAIPackService:
    def __init__(
        self,
        tools: dict[str, ToolStatus],
        config: dict,
        *,
        metadata_reader: MetadataReader = read_media_metadata,
        keyframe_generator: KeyframeGenerator = generate_keyframe_artifacts,
        audio_probe: AudioProbe = probe_audio_stream,
        audio_extractor: ArtifactGenerator = extract_audio,
        proxy_generator: ArtifactGenerator = create_proxy,
        logger: DiagnosticLogger | None = None,
    ) -> None:
        self.tools = tools
        self.config = config
        self.metadata_reader = metadata_reader
        self.keyframe_generator = keyframe_generator
        self.audio_probe = audio_probe
        self.audio_extractor = audio_extractor
        self.proxy_generator = proxy_generator
        self.logger = logger

    def _path(self, name: str) -> str | None:
        status = self.tools.get(name)
        return status.path if status else None

    def plan(self, job: Job) -> VideoAIPackPlan:
        if job.operation is not Operation.VIDEO_AI_PACK:
            raise ValueError(f"Video AI Pack service cannot execute {job.operation.name}")
        video = self.config.get("video", {})
        return VideoAIPackPlan(
            sources=job.input_sources,
            output_root=job.output_root,
            include_audio=(
                job.video_ai_pack_include_audio
                if job.video_ai_pack_include_audio is not None
                else bool(video.get("ai_pack_include_audio", True))
            ),
            include_proxy=(
                job.video_ai_pack_include_proxy
                if job.video_ai_pack_include_proxy is not None
                else bool(video.get("ai_pack_include_proxy", False))
            ),
            proxy_crf=(
                job.video_ai_pack_proxy_crf
                if job.video_ai_pack_proxy_crf is not None
                else int(video.get("ai_pack_proxy_crf", 28))
            ),
            scene_threshold=(
                float(job.video_ai_pack_scene_threshold)
                if job.video_ai_pack_scene_threshold is not None
                else float(video.get("scene_threshold", 0.30))
            ),
            max_keyframes=(
                job.video_ai_pack_max_keyframes
                if job.video_ai_pack_max_keyframes is not None
                else int(video.get("max_keyframes", 24))
            ),
            contact_sheet_columns=int(video.get("contact_sheet_columns", 4)),
        )

    def _metadata_payload(self, source: VideoPackSource) -> dict[str, object]:
        metadata = source.metadata
        payload: dict[str, object] = {
            "source_id": source.source_id,
            "display_name": source.display_name,
            "extension": source.path.suffix.lower(),
            "file_size": source.path.stat().st_size,
            "duration_seconds": metadata.duration_seconds,
            "width": metadata.width,
            "height": metadata.height,
            "resolution": metadata.resolution or None,
            "codec": metadata.codec or None,
            "frame_rate": metadata.frame_rate,
            "capture_time": metadata.captured_at.isoformat(timespec="seconds"),
            "capture_time_source": metadata.capture_time_source,
            "camera": metadata.camera or None,
            "make": metadata.make or None,
            "model": metadata.model or None,
            "location_label": metadata.location_label or None,
            "metadata_source": metadata.source,
            "source_sha256": source.source_sha256,
            "warnings": [],
        }
        if metadata.latitude is not None and metadata.longitude is not None:
            payload.update(
                {
                    "latitude": metadata.latitude,
                    "longitude": metadata.longitude,
                    "gps_origin": "embedded_source_metadata",
                    "gps_network_shared": False,
                }
            )
        return payload

    def _record_optional_failure(
        self,
        event: str,
        exc: Exception,
        source: Path,
        *,
        tool: str,
    ) -> None:
        if self.logger is not None:
            self.logger.record_failure(
                event,
                exc,
                source_suffix=source.suffix,
                tool=tool,
            )

    def create_pack(
        self,
        job: Job,
        index: int = 1,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> VideoAIPackResult:
        del index
        plan = self.plan(job)
        _raise_if_cancelled(cancellation)
        plan.output_root.mkdir(parents=True, exist_ok=True)
        final_output = unique_path(plan.output_root / "Video-AI-Pack")
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{final_output.name}.tmp-", dir=plan.output_root)
        )
        try:
            if on_progress:
                on_progress(5, "正在读取视频信息")
            pack_sources: list[VideoPackSource] = []
            for source_index, source_path in enumerate(plan.sources, start=1):
                _raise_if_cancelled(cancellation)
                source_hash = _sha256(source_path, cancellation)
                metadata = self.metadata_reader(
                    source_path,
                    self._path("exiftool"),
                    self._path("ffprobe"),
                    ffmpeg=self._path("ffmpeg"),
                    cancellation=cancellation,
                    logger=self.logger,
                )
                _raise_if_cancelled(cancellation)
                pack_sources.append(
                    VideoPackSource(
                        f"video-{source_index:03d}",
                        source_path.name,
                        source_path,
                        metadata,
                        source_hash,
                    )
                )

            warnings: list[VideoPackWarning] = []
            frames: list[VideoFrame] = []
            timeline: list[VideoTimelineEntry] = []
            artifacts: list[dict[str, object]] = []
            statuses: list[dict[str, object]] = []
            source_manifests: list[dict[str, object]] = []
            aggregate_metadata: list[dict[str, object]] = []

            for source_index, source in enumerate(pack_sources, start=1):
                _raise_if_cancelled(cancellation)
                if on_progress:
                    on_progress(
                        10 + round((source_index - 1) / max(1, len(pack_sources)) * 65),
                        f"正在处理第 {source_index} 个视频",
                    )
                source_root = temporary / "sources" / source.source_id
                frames_dir = source_root / "frames"
                source_root.mkdir(parents=True)
                metadata_payload = self._metadata_payload(source)

                audio_status: dict[str, object] = {
                    "source_id": source.source_id,
                    "artifact_type": "audio",
                    "requested": plan.include_audio,
                    "status": "not_requested",
                    "path": None,
                }
                if plan.include_audio:
                    if on_progress:
                        on_progress(20, "正在提取音频")
                    has_audio: bool | None = None
                    try:
                        has_audio = self.audio_probe(
                            source.path,
                            self._path("ffprobe"),
                            cancellation=cancellation,
                        )
                    except Exception as exc:
                        _raise_if_fatal_optional_failure(exc, cancellation)
                        self._record_optional_failure(
                            "video_ai_pack.audio_probe_failed", exc, source.path, tool="ffprobe"
                        )
                    if has_audio is False:
                        audio_status["status"] = "unavailable"
                        warnings.append(
                            VideoPackWarning(
                                "audio_unavailable",
                                "未检测到音轨；未生成空音频文件。",
                                source.source_id,
                            )
                        )
                    else:
                        try:
                            audio_dir = source_root / "audio"
                            audio_path = self.audio_extractor(
                                source.path,
                                audio_dir,
                                self._path("ffmpeg"),
                                "wav",
                                "192k",
                                cancellation=cancellation,
                                duration_seconds=float(source.metadata.duration_seconds or 0.0),
                            )
                            audio_path = _confined_generated_file(temporary, audio_dir, audio_path)
                            canonical_audio_path = audio_dir / "audio.wav"
                            _relative(temporary, canonical_audio_path)
                            if audio_path != canonical_audio_path:
                                os.replace(audio_path, canonical_audio_path)
                                audio_path = canonical_audio_path
                            audio_relative = _relative(temporary, audio_path)
                            audio_status.update(status="generated", path=audio_relative)
                            artifacts.append(
                                {
                                    "type": "audio",
                                    "source_id": source.source_id,
                                    "path": audio_relative,
                                }
                            )
                        except Exception as exc:
                            _raise_if_fatal_optional_failure(exc, cancellation)
                            shutil.rmtree(source_root / "audio", ignore_errors=True)
                            self._record_optional_failure(
                                "video_ai_pack.audio_extraction_failed",
                                exc,
                                source.path,
                                tool="ffmpeg",
                            )
                            audio_status["status"] = "failed"
                            warnings.append(
                                VideoPackWarning(
                                    "audio_extraction_failed",
                                    "音频提取失败；资料包仍包含其他核心内容。",
                                    source.source_id,
                                )
                            )
                statuses.append(audio_status)

                if on_progress:
                    on_progress(35, "正在提取关键帧")
                keyframes = self.keyframe_generator(
                    source.path,
                    frames_dir,
                    source_root / "contact-sheet.jpg",
                    self._path("ffmpeg"),
                    scene_threshold=plan.scene_threshold,
                    max_frames=plan.max_keyframes,
                    columns=plan.contact_sheet_columns,
                    frame_prefix="frame-",
                    cancellation=cancellation,
                    duration_seconds=float(source.metadata.duration_seconds or 0.0),
                    progress_callback=(
                        (lambda _value, message: on_progress(50, message)) if on_progress else None
                    ),
                    logger=self.logger,
                )
                _raise_if_cancelled(cancellation)
                if keyframes.used_first_frame_fallback:
                    warnings.append(
                        VideoPackWarning(
                            "first_frame_fallback",
                            "未检测到确定性 scene-change 关键帧，已使用视频首帧。",
                            source.source_id,
                        )
                    )
                elif keyframes.scene_detection_failed:
                    warnings.append(
                        VideoPackWarning(
                            "scene_detection_failed",
                            "scene-change 提取未完整完成；保留了已生成的确定性帧。",
                            source.source_id,
                        )
                    )
                contact_relative = _relative(temporary, keyframes.contact_sheet)
                artifacts.append(
                    {
                        "type": "contact_sheet",
                        "source_id": source.source_id,
                        "path": contact_relative,
                    }
                )
                source_frames: list[dict[str, object]] = []
                for frame_index, frame_path in enumerate(keyframes.frames, start=1):
                    timestamp = (
                        keyframes.timestamps[frame_index - 1]
                        if frame_index - 1 < len(keyframes.timestamps)
                        else None
                    )
                    frame_id = f"{source.source_id}-frame-{frame_index:03d}"
                    frame_relative = _relative(temporary, frame_path)
                    frame = VideoFrame(
                        source.source_id,
                        frame_id,
                        frame_relative,
                        timestamp,
                    )
                    entry = VideoTimelineEntry(
                        source.source_id,
                        frame_id,
                        timestamp,
                        _timestamp_label(timestamp),
                        frame_relative,
                    )
                    frames.append(frame)
                    timeline.append(entry)
                    source_frames.append(
                        {
                            "frame_id": frame_id,
                            "timestamp_seconds": timestamp,
                            "path": frame_relative,
                        }
                    )
                    artifacts.append(
                        {
                            "type": "frame",
                            "source_id": source.source_id,
                            "frame_id": frame_id,
                            "path": frame_relative,
                        }
                    )

                proxy_status: dict[str, object] = {
                    "source_id": source.source_id,
                    "artifact_type": "proxy",
                    "requested": plan.include_proxy,
                    "status": "not_requested",
                    "path": None,
                }
                if plan.include_proxy:
                    try:
                        if on_progress:
                            on_progress(65, "正在生成压缩 proxy")
                        proxy_path = self.proxy_generator(
                            source.path,
                            source_root / "proxy",
                            self._path("ffmpeg"),
                            plan.proxy_crf,
                            cancellation=cancellation,
                            duration_seconds=float(source.metadata.duration_seconds or 0.0),
                        )
                        proxy_path = _confined_generated_file(
                            temporary, source_root / "proxy", proxy_path
                        )
                        proxy_relative = _relative(temporary, proxy_path)
                        proxy_status.update(status="generated", path=proxy_relative)
                        artifacts.append(
                            {
                                "type": "proxy",
                                "source_id": source.source_id,
                                "path": proxy_relative,
                            }
                        )
                    except Exception as exc:
                        _raise_if_fatal_optional_failure(exc, cancellation)
                        shutil.rmtree(source_root / "proxy", ignore_errors=True)
                        self._record_optional_failure(
                            "video_ai_pack.proxy_generation_failed",
                            exc,
                            source.path,
                            tool="ffmpeg",
                        )
                        proxy_status["status"] = "failed"
                        warnings.append(
                            VideoPackWarning(
                                "proxy_generation_failed",
                                "压缩 proxy 生成失败；核心资料包仍然可用。",
                                source.source_id,
                            )
                        )
                statuses.append(proxy_status)

                source_metadata_path = source_root / "metadata.json"
                source_warnings = [
                    asdict(warning) for warning in warnings if warning.source_id == source.source_id
                ]
                metadata_payload["warnings"] = source_warnings
                aggregate_metadata.append(metadata_payload)
                source_payload = {
                    **metadata_payload,
                    "audio": audio_status,
                    "proxy": proxy_status,
                    "contact_sheet": contact_relative,
                    "frames": source_frames,
                }
                _write_json(source_metadata_path, source_payload)
                source_metadata_relative = _relative(temporary, source_metadata_path)
                artifacts.append(
                    {
                        "type": "source_metadata",
                        "source_id": source.source_id,
                        "path": source_metadata_relative,
                    }
                )
                source_manifests.append(
                    {
                        "source_id": source.source_id,
                        "display_name": source.display_name,
                        "metadata": source_metadata_relative,
                        "contact_sheet": contact_relative,
                        "frames": source_frames,
                        "audio": audio_status,
                        "proxy": proxy_status,
                    }
                )

            if on_progress:
                on_progress(78, "正在生成 timeline")
            timeline_path = temporary / "timeline.json"
            _write_json(
                timeline_path,
                {
                    "package_type": "video_ai_pack_timeline",
                    "video_ai_pack_version": VIDEO_AI_PACK_VERSION,
                    "semantics": "deterministic_scene_change_frames_per_source",
                    "entries": [asdict(entry) for entry in timeline],
                },
            )
            metadata_path = temporary / "metadata.json"
            _write_json(
                metadata_path,
                {
                    "package_type": "video_ai_pack_metadata",
                    "video_ai_pack_version": VIDEO_AI_PACK_VERSION,
                    "sources": aggregate_metadata,
                },
            )
            start_here = temporary / "START_HERE.md"
            audio_count = sum(status.get("status") == "generated" for status in statuses[::2])
            proxy_count = sum(status.get("status") == "generated" for status in statuses[1::2])
            known_duration = sum(
                float(source.metadata.duration_seconds)
                for source in pack_sources
                if source.metadata.duration_seconds is not None
            )
            warning_text = (
                "\n".join(
                    f"- {warning.source_id or 'pack'}: {warning.message}" for warning in warnings
                )
                or "- None"
            )
            start_here.write_text(
                "# Video AI Pack\n\n"
                f"Sources: {len(pack_sources)}\n"
                f"Frames: {len(frames)}\n"
                f"Audio tracks: {audio_count}\n"
                f"Proxy videos: {proxy_count}\n"
                + (f"Known duration: {known_duration:.3f} seconds\n" if known_duration else "")
                + "\n## Source inventory\n\n"
                + "\n".join(
                    f"- `{source.source_id}` — {source.display_name}" for source in pack_sources
                )
                + "\n\n## Warnings\n\n"
                + warning_text
                + "\n\n## Suggested order\n\n"
                "1. Read `manifest.json`\n"
                "2. Read `timeline.json`\n"
                "3. Review contact sheets\n"
                "4. Upload individual frames or audio when needed\n\n"
                "Frames are selected using deterministic scene-change detection.\n"
                "The timeline keeps each source separate and does not represent semantic scenes.\n"
                "No semantic scene understanding or AI summary was performed.\n"
                "Original videos were not copied into this package and were not modified.\n"
                "Embedded GPS metadata, when present, remains local and is not sent to a network service.\n",
                encoding="utf-8",
            )
            for artifact_type, path in (
                ("timeline", timeline_path),
                ("metadata", metadata_path),
                ("start_here", start_here),
            ):
                artifacts.append(
                    {
                        "type": artifact_type,
                        "source_id": None,
                        "path": _relative(temporary, path),
                    }
                )

            _raise_if_cancelled(cancellation)
            if on_progress:
                on_progress(88, "正在验证资料包")
            hashes_unchanged = all(
                _sha256(source.path, cancellation) == source.source_sha256
                for source in pack_sources
            )
            artifact_paths = [str(item["path"]) for item in artifacts]
            integrity = validate_video_ai_pack(
                temporary,
                source_ids=(source.source_id for source in pack_sources),
                frames=frames,
                timeline=timeline,
                artifacts=artifact_paths,
                statuses=statuses,
                source_hashes_unchanged=hashes_unchanged,
            )
            if not integrity.ok:
                raise UserFacingError(
                    ErrorCode.INTEGRITY_FAILED,
                    "视频 AI 资料包完整性验证未通过，未发布不完整结果。",
                )

            created_at = datetime.now().astimezone().isoformat(timespec="seconds")
            warning_payload = [asdict(warning) for warning in warnings]
            integrity_payload = asdict(integrity)
            options = {
                "include_audio": plan.include_audio,
                "audio_format": "wav_pcm_s16le",
                "include_proxy": plan.include_proxy,
                "proxy_crf": plan.proxy_crf,
                "scene_threshold": plan.scene_threshold,
                "max_keyframes_per_source": plan.max_keyframes,
                "contact_sheet_columns": plan.contact_sheet_columns,
            }
            manifest = {
                "package_type": "video_ai_pack",
                "video_ai_pack_version": VIDEO_AI_PACK_VERSION,
                "created_at": created_at,
                "source_count": len(pack_sources),
                "sources": source_manifests,
                "artifacts": artifacts,
                "timeline": "timeline.json",
                "warnings": warning_payload,
                "integrity": integrity_payload,
                "options": options,
            }
            _write_json(temporary / "manifest.json", manifest)
            validate_written_video_ai_pack_manifest(
                temporary,
                source_ids=(source.source_id for source in pack_sources),
                frames=frames,
                artifact_paths=artifact_paths,
            )
            _raise_if_cancelled(cancellation)
            if on_progress:
                on_progress(96, "正在写入结果")
            os.replace(temporary, final_output)
            report: dict[str, Any] = {
                "video_ai_pack_version": VIDEO_AI_PACK_VERSION,
                "source_count": len(pack_sources),
                "frame_count": len(frames),
                "audio_count": audio_count,
                "proxy_count": proxy_count,
                "warnings": warning_payload,
                "integrity": integrity_payload,
            }
            return VideoAIPackResult(final_output, report)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
            raise
