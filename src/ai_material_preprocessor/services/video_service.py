from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..converters.video import (
    compress,
    extract_audio,
    keyframes_contact_sheet,
    organize_copy,
    probe_duration,
    rename_copy,
    standardize,
)
from ..infrastructure.processes import CancellationToken
from ..models import Job, Operation, ToolStatus


class VideoProcessingService:
    def __init__(self, tools: dict[str, ToolStatus], config: dict) -> None:
        self.tools = tools
        self.config = config

    def _path(self, name: str) -> str | None:
        status = self.tools.get(name)
        return status.path if status else None

    def convert(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> Path:
        video = self.config["video"]
        duration = 0.0
        if self._path("ffprobe"):
            try:
                duration = probe_duration(
                    str(self._path("ffprobe")),
                    job.source,
                    cancellation=cancellation,
                )
            except Exception:
                if cancellation and cancellation.is_cancelled:
                    raise
        if job.operation is Operation.COMPRESS_VIDEO:
            return compress(
                job.source,
                job.output_root,
                self._path("ffmpeg"),
                int(video["compression_crf"]),
                str(video["compression_preset"]),
                cancellation=cancellation,
                duration_seconds=duration,
                progress_callback=on_progress,
            )
        if job.operation is Operation.EXTRACT_AUDIO:
            return extract_audio(
                job.source,
                job.output_root,
                self._path("ffmpeg"),
                str(video["audio_format"]),
                str(video["audio_bitrate"]),
                cancellation=cancellation,
                duration_seconds=duration,
                progress_callback=on_progress,
            )
        if job.operation is Operation.STANDARDIZE_MP4:
            return standardize(
                job.source,
                job.output_root,
                self._path("ffmpeg"),
                cancellation=cancellation,
                duration_seconds=duration,
                progress_callback=on_progress,
            )
        if job.operation is Operation.KEYFRAMES_CONTACT_SHEET:
            return keyframes_contact_sheet(
                job.source,
                job.output_root,
                self._path("ffmpeg"),
                scene_threshold=float(video["scene_threshold"]),
                max_frames=int(video["max_keyframes"]),
                columns=int(video["contact_sheet_columns"]),
                cancellation=cancellation,
                duration_seconds=duration,
                progress_callback=on_progress,
            )
        if job.operation is Operation.RENAME_VIDEO:
            return rename_copy(
                job.source,
                job.output_root,
                self._path("ffprobe"),
                job.location,
                index,
                exiftool=self._path("exiftool"),
                ffmpeg=self._path("ffmpeg"),
                template=str(video["rename_template"]),
                project_name=job.project or str(video.get("project_name", "")),
                location_dictionary=dict(video.get("location_dictionary", {})),
                cancellation=cancellation,
            )
        if job.operation is Operation.ORGANIZE_VIDEO:
            return organize_copy(
                job.source,
                job.output_root,
                self._path("ffprobe"),
                job.location,
                index,
                exiftool=self._path("exiftool"),
                ffmpeg=self._path("ffmpeg"),
                template=str(video["rename_template"]),
                project_name=job.project or str(video.get("project_name", "")),
                organize_mode=str(video.get("organize_mode", "date_location")),
                location_dictionary=dict(video.get("location_dictionary", {})),
                cancellation=cancellation,
            )
        raise ValueError(f"Video service cannot execute {job.operation.name}")
