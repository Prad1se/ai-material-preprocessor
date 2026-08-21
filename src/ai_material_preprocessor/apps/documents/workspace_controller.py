from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...application.workspace_inputs import WorkspaceInputSelection, classify_workspace_inputs
from ...application.workspaces import WorkspaceId
from ...capabilities import available_operations
from ...converters.video import VIDEO_EXTENSIONS
from ...models import Job, Operation, ToolStatus
from .policy import DOCUMENT_INPUT_EXTENSIONS, DOCUMENT_OPERATIONS


class DocumentWorkspaceController:
    allowed_operations = DOCUMENT_OPERATIONS
    supported_extensions = DOCUMENT_INPUT_EXTENSIONS

    def __init__(self, tools: dict[str, ToolStatus]) -> None:
        self.tools = tools

    def update_tools(self, tools: dict[str, ToolStatus]) -> None:
        self.tools = tools

    def classify_inputs(self, paths: list[str]) -> WorkspaceInputSelection:
        return classify_workspace_inputs(
            paths,
            supported_extensions=DOCUMENT_INPUT_EXTENSIONS,
            foreign_extensions=frozenset(VIDEO_EXTENSIONS),
            foreign_workspace=WorkspaceId.VIDEO,
        )

    def operations_for(self, paths: list[Path]) -> list[Operation]:
        if not paths:
            return []
        available = [
            set(available_operations(path, self.tools, allowed_operations=DOCUMENT_OPERATIONS))
            for path in paths
        ]
        common = set.intersection(*available) if available else set()
        return [operation for operation in Operation if operation in common]

    @staticmethod
    def create_jobs(
        paths: list[Path],
        operation: Operation,
        output_for: Callable[[Path], Path],
    ) -> list[Job]:
        if operation not in DOCUMENT_OPERATIONS:
            raise ValueError(f"{operation.name} is not a document operation.")
        return [Job(path, operation, output_for(path)) for path in paths]
