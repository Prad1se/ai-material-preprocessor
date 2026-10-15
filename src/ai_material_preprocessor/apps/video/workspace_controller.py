from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...application.workspace_inputs import WorkspaceInputSelection, classify_workspace_inputs
from ...application.workspaces import WorkspaceId
from ...capabilities import available_operations
from ...converters.markdown import SUPPORTED_EXTENSIONS as MARKDOWN_EXTENSIONS
from ...converters.office_pdf import POWERPOINT_EXTENSIONS, WORD_EXTENSIONS
from ...models import Job, Operation, ToolStatus
from .policy import VIDEO_INPUT_EXTENSIONS, VIDEO_OPERATIONS


class VideoWorkspaceController:
    allowed_operations = VIDEO_OPERATIONS
    supported_extensions = VIDEO_INPUT_EXTENSIONS

    def __init__(self, tools: dict[str, ToolStatus]) -> None:
        self.tools = tools

    def update_tools(self, tools: dict[str, ToolStatus]) -> None:
        self.tools = tools

    def classify_inputs(self, paths: list[str]) -> WorkspaceInputSelection:
        return classify_workspace_inputs(
            paths,
            supported_extensions=VIDEO_INPUT_EXTENSIONS,
            foreign_extensions=frozenset(
                MARKDOWN_EXTENSIONS | WORD_EXTENSIONS | POWERPOINT_EXTENSIONS
            ),
            foreign_workspace=WorkspaceId.DOCUMENTS,
        )

    def operations_for(self, paths: list[Path]) -> list[Operation]:
        if not paths:
            return []
        available = [
            set(available_operations(path, self.tools, allowed_operations=VIDEO_OPERATIONS))
            for path in paths
        ]
        common = set.intersection(*available) if available else set()
        return [operation for operation in Operation if operation in common]

    @staticmethod
    def create_jobs(
        paths: list[Path],
        operation: Operation,
        output_for: Callable[[Path], Path],
        *,
        location: str = "",
        project: str = "",
        include_audio: bool | None = None,
        include_proxy: bool | None = None,
        proxy_crf: int | None = None,
        scene_threshold: float | None = None,
        max_keyframes: int | None = None,
    ) -> list[Job]:
        if operation not in VIDEO_OPERATIONS:
            raise ValueError(f"{operation.name} is not a video operation.")
        if operation is Operation.VIDEO_AI_PACK:
            if not paths:
                return []
            return [
                Job(
                    paths[0],
                    operation,
                    output_for(paths[0]),
                    sources=tuple(paths),
                    video_ai_pack_include_audio=include_audio,
                    video_ai_pack_include_proxy=include_proxy,
                    video_ai_pack_proxy_crf=proxy_crf,
                    video_ai_pack_scene_threshold=scene_threshold,
                    video_ai_pack_max_keyframes=max_keyframes,
                )
            ]
        return [
            Job(path, operation, output_for(path), location=location, project=project)
            for path in paths
        ]
