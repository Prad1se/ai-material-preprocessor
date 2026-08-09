from __future__ import annotations

from pathlib import Path

from ..converters.video import (
    compress,
    extract_audio,
    keyframes_contact_sheet,
    rename_copy,
    standardize,
)
from ..models import Job, Operation, ToolStatus


class VideoProcessingService:
    def __init__(self, tools: dict[str, ToolStatus], config: dict) -> None:
        self.tools = tools
        self.config = config

    def _path(self, name: str) -> str | None:
        status = self.tools.get(name)
        return status.path if status else None

    def convert(self, job: Job, index: int) -> Path:
        video = self.config["video"]
        if job.operation is Operation.COMPRESS_VIDEO:
            return compress(
                job.source,
                job.output_root,
                self._path("ffmpeg"),
                int(video["compression_crf"]),
                str(video["compression_preset"]),
            )
        if job.operation is Operation.EXTRACT_AUDIO:
            return extract_audio(
                job.source,
                job.output_root,
                self._path("ffmpeg"),
                str(video["audio_format"]),
                str(video["audio_bitrate"]),
            )
        if job.operation is Operation.STANDARDIZE_MP4:
            return standardize(job.source, job.output_root, self._path("ffmpeg"))
        if job.operation is Operation.KEYFRAMES_CONTACT_SHEET:
            return keyframes_contact_sheet(
                job.source,
                job.output_root,
                self._path("ffmpeg"),
                scene_threshold=float(video["scene_threshold"]),
                max_frames=int(video["max_keyframes"]),
                columns=int(video["contact_sheet_columns"]),
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
            )
        raise ValueError(f"Video service cannot execute {job.operation.name}")
