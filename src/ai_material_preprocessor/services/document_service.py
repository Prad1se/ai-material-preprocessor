from __future__ import annotations

from pathlib import Path

from ..converters.markdown import to_markdown
from ..converters.office_pdf import to_pdf
from ..infrastructure.processes import CancellationToken
from ..models import Job, Operation, ToolStatus
from .document_enhancement import EnhancementOptions


class DocumentConversionService:
    def __init__(self, tools: dict[str, ToolStatus], config: dict) -> None:
        self.tools = tools
        self.config = config

    def _path(self, name: str) -> str | None:
        status = self.tools.get(name)
        return status.path if status else None

    def convert(
        self,
        job: Job,
        *,
        cancellation: CancellationToken | None = None,
    ) -> tuple[Path, list[dict]]:
        if job.operation is Operation.TO_MARKDOWN:
            document = self.config["document"]
            reports: list[dict] = []
            result = to_markdown(
                job.source,
                job.output_root,
                self._path("markitdown"),
                enhance=str(document["mode"]) == "enhanced",
                enhancement_options=EnhancementOptions(
                    split_enabled=bool(document["split_enabled"]),
                    target_tokens=int(document["target_tokens"]),
                    max_tokens=int(document["max_tokens"]),
                    ocr_enabled=bool(document["ocr_enabled"]),
                ),
                quality_callback=lambda report: reports.append(
                    {"source": job.source.name, **report.to_dict()}
                ),
                cancellation=cancellation,
            )
            return result, reports
        if job.operation is Operation.TO_PDF:
            result = to_pdf(
                job.source,
                job.output_root,
                self._path("libreoffice"),
                self._path("winword"),
                self._path("powerpoint"),
                cancellation=cancellation,
            )
            return result, []
        raise ValueError(f"Document service cannot execute {job.operation.name}")
