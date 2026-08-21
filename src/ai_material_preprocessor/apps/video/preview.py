from __future__ import annotations

from dataclasses import dataclass

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
