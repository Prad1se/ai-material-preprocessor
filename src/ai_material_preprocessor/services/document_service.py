from __future__ import annotations

from pathlib import Path

from ..converters.markdown import to_markdown
from ..converters.office_pdf import to_pdf
from ..infrastructure.processes import CancellationToken
from ..models import Job, Operation, ToolStatus
from .document_enhancement import EnhancementOptions
from .preview import (
    build_document_preview,
    document_preview_to_dict,
    ocr_pages_from_markdown,
)


class DocumentConversionService:
    def __init__(self, tools: dict[str, ToolStatus], config: dict) -> None:
        self.tools = tools
        self.config = config

    def _path(self, name: str) -> str | None:
        status = self.tools.get(name)
        return status.path if status else None

    def _document_tool_versions(self, *, include_ocr: bool) -> dict[str, str]:
        names = [("markitdown", "MarkItDown")]
        if include_ocr:
            names.append(("rapidocr", "RapidOCR"))
        return {
            display_name: status.version
            for key, display_name in names
            if (status := self.tools.get(key)) is not None and status.version
        }

    def convert(
        self,
        job: Job,
        *,
        cancellation: CancellationToken | None = None,
    ) -> tuple[Path, list[dict]]:
        if job.operation is Operation.TO_MARKDOWN:
            document = self.config["document"]
            enhanced = str(document["mode"]) == "enhanced"
            options = EnhancementOptions(
                split_enabled=bool(document["split_enabled"]) if enhanced else False,
                target_tokens=int(document["target_tokens"]),
                max_tokens=int(document["max_tokens"]),
                ocr_enabled=bool(document["ocr_enabled"]) if enhanced else False,
            )
            result = to_markdown(
                job.source,
                job.output_root,
                self._path("markitdown"),
                enhance=enhanced,
                enhancement_options=options,
                cancellation=cancellation,
                tool_versions=self._document_tool_versions(include_ocr=options.ocr_enabled),
            )
            markdown = result.read_text(encoding="utf-8")
            preview = build_document_preview(
                job.source,
                markdown,
                base_dir=result.parent,
                options=options,
                ocr_pages=ocr_pages_from_markdown(markdown),
                parameters={
                    "模式": "AI 增强" if enhanced else "原始转换",
                    "自动拆分": "是" if options.split_enabled else "否",
                    "目标长度": f"{options.target_tokens} tokens",
                    "OCR": "开启" if options.ocr_enabled else "关闭",
                },
            )
            return result, [document_preview_to_dict(preview)]
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
