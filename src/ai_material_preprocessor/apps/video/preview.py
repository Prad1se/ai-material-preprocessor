from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...application.preview_registry import PreviewRequest
from ...models import Operation
from ...preview_models import VideoPreview
from ...services.metadata import read_media_metadata
from ...services.preview import (
    build_batch_rename_preview,
    build_video_preview,
    resolve_batch_output_collisions,
)
from ...services.video_management import annotate_duplicate_previews, find_duplicate_videos


@dataclass(frozen=True)
class VideoPreviewBatch:
    previews: tuple[VideoPreview, ...]


@dataclass(frozen=True)
class VideoAIPackPreviewPlan:
    title: str
    sources: tuple[Path, ...]
    parameters: dict[str, str]
    note: str


class VideoAIPackPreviewProvider:
    def build(self, request: PreviewRequest) -> VideoAIPackPreviewPlan:
        metadata = [
            read_media_metadata(
                source,
                request.tool_paths.get("exiftool"),
                request.tool_paths.get("ffprobe"),
                ffmpeg=request.tool_paths.get("ffmpeg"),
            )
            for source in request.sources
        ]
        details = []
        for index, (source, values) in enumerate(
            zip(request.sources, metadata, strict=True), start=1
        ):
            facts = [source.name]
            if values.duration_seconds is not None:
                facts.append(f"{values.duration_seconds:.3f} 秒")
            if values.resolution:
                facts.append(values.resolution)
            if values.codec:
                facts.append(values.codec)
            details.append(f"video-{index:03d}: " + " · ".join(facts))
        parameters = dict(request.parameters)
        parameters["视频数量"] = str(len(request.sources))
        parameters["来源概览"] = "\n".join(details)
        parameters["输出位置"] = str(request.output_root)
        return VideoAIPackPreviewPlan(
            "视频 AI 资料包预览",
            request.sources,
            {key: str(value) for key, value in parameters.items()},
            "实际关键帧数量和音轨可用性将在处理后确定。关键帧仅来自确定性 "
            "scene-change 检测；不会进行语义理解、AI 总结或网络上传。",
        )


class VideoPreviewProvider:
    def build(self, request: PreviewRequest) -> VideoPreviewBatch:
        exiftool = request.tool_paths.get("exiftool")
        ffprobe = request.tool_paths.get("ffprobe")
        ffmpeg = request.tool_paths.get("ffmpeg")
        metadata = [
            read_media_metadata(source, exiftool, ffprobe, ffmpeg=ffmpeg)
            for source in request.sources
        ]
        parameters = dict(request.parameters)
        if request.operation is Operation.RENAME_VIDEO:
            raw_dictionary = parameters.get("location_dictionary", {})
            location_dictionary = (
                {str(key): str(value) for key, value in raw_dictionary.items()}
                if isinstance(raw_dictionary, dict)
                else {}
            )
            previews = list(
                build_batch_rename_preview(
                    request.sources,
                    metadata,
                    request.output_root,
                    template=str(
                        parameters.get("rename_template") or "{date}_{time}_{location}_{index}"
                    ),
                    manual_location=request.manual_location,
                    project_name=str(parameters.get("project_name") or ""),
                    location_dictionary=location_dictionary,
                )
            )
        else:
            previews = [
                build_video_preview(
                    source,
                    item,
                    request.operation,
                    request.output_root,
                    parameters=parameters,
                    index=index,
                    manual_location=request.manual_location,
                )
                for index, (source, item) in enumerate(
                    zip(request.sources, metadata, strict=True), start=1
                )
            ]
        previews = list(resolve_batch_output_collisions(previews))
        previews = list(
            annotate_duplicate_previews(
                previews, find_duplicate_videos(list(request.sources), metadata)
            )
        )
        return VideoPreviewBatch(tuple(previews))
