from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...application.workspace_inputs import WorkspaceInputSelection, classify_workspace_inputs
from ...application.workspaces import WorkspaceId
from ...capabilities import available_operations
from ...converters.markdown import SUPPORTED_EXTENSIONS as MARKDOWN_EXTENSIONS
from ...converters.office_pdf import POWERPOINT_EXTENSIONS, WORD_EXTENSIONS
from ...converters.video import VIDEO_EXTENSIONS
from ...models import Job, Operation, ToolStatus
from .policy import DOCUMENT_INPUT_EXTENSIONS, DOCUMENT_OPERATIONS


@dataclass(frozen=True)
class DocumentOperationAvailability:
    operation: Operation
    available: bool
    reason: str = ""


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

    def operation_availability(self, paths: list[Path]) -> list[DocumentOperationAvailability]:
        if not paths:
            return []
        suffixes = {path.suffix.lower() for path in paths}
        candidates: list[Operation] = []
        if suffixes <= MARKDOWN_EXTENSIONS:
            candidates.extend((Operation.TO_MARKDOWN, Operation.DOCUMENT_CONTEXT_PACK))
        if suffixes <= (WORD_EXTENSIONS | POWERPOINT_EXTENSIONS):
            candidates.append(Operation.TO_PDF)

        available = set(self.operations_for(paths))
        return [
            DocumentOperationAvailability(
                operation,
                operation in available,
                "" if operation in available else self._missing_reason(operation, suffixes),
            )
            for operation in candidates
        ]

    def _missing_reason(self, operation: Operation, suffixes: set[str]) -> str:
        if operation in {Operation.TO_MARKDOWN, Operation.DOCUMENT_CONTEXT_PACK}:
            return "Microsoft MarkItDown is required. Open Documents Settings to set it up."
        missing: list[str] = []
        libreoffice = self.tools.get("libreoffice", ToolStatus("libreoffice", None)).available
        if suffixes & WORD_EXTENSIONS and not (
            libreoffice or self.tools.get("winword", ToolStatus("winword", None)).available
        ):
            missing.append("Microsoft Word or LibreOffice")
        if suffixes & POWERPOINT_EXTENSIONS and not (
            libreoffice or self.tools.get("powerpoint", ToolStatus("powerpoint", None)).available
        ):
            missing.append("Microsoft PowerPoint or LibreOffice")
        return (
            " and ".join(missing) + " required. Open Documents Settings to set it up."
            if missing
            else "A required document tool is unavailable."
        )

    @staticmethod
    def create_jobs(
        paths: list[Path],
        operation: Operation,
        output_for: Callable[[Path], Path],
        *,
        context_budget: int | None = None,
        context_ocr_enabled: bool | None = None,
    ) -> list[Job]:
        if operation not in DOCUMENT_OPERATIONS:
            raise ValueError(f"{operation.name} is not a document operation.")
        if not paths:
            return []
        if operation is Operation.DOCUMENT_CONTEXT_PACK:
            return [
                Job(
                    paths[0],
                    operation,
                    output_for(paths[0]),
                    sources=tuple(paths),
                    context_budget=context_budget,
                    context_ocr_enabled=context_ocr_enabled,
                )
            ]
        return [Job(path, operation, output_for(path)) for path in paths]
