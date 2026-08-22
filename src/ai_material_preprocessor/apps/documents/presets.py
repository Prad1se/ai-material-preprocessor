"""Document Workspace parameter templates built from existing pipeline options."""

from __future__ import annotations

from dataclasses import dataclass

from ...models import Operation


@dataclass(frozen=True)
class DocumentPreset:
    preset_id: str
    label: str
    description: str
    operation: Operation
    context_budget: int
    ocr_enabled: bool


DOCUMENT_PRESETS = (
    DocumentPreset(
        preset_id="research_paper",
        label="研究论文",
        description=("创建可追溯的 AI 上下文包；如果本地 OCR 可用则启用，并使用 128K 上下文预算。"),
        operation=Operation.DOCUMENT_CONTEXT_PACK,
        context_budget=128000,
        ocr_enabled=True,
    ),
    DocumentPreset(
        preset_id="course_notes",
        label="课程笔记",
        description=("将结构化笔记整理为 AI 就绪 Markdown，并按 64K 上下文预算分包。"),
        operation=Operation.DOCUMENT_CONTEXT_PACK,
        context_budget=64000,
        ocr_enabled=False,
    ),
    DocumentPreset(
        preset_id="coding_documents",
        label="编程文档",
        description=("保留围栏代码块，关闭 OCR，并按 64K 上下文预算创建上传包。"),
        operation=Operation.DOCUMENT_CONTEXT_PACK,
        context_budget=64000,
        ocr_enabled=False,
    ),
)

PRESET_BY_ID = {preset.preset_id: preset for preset in DOCUMENT_PRESETS}
