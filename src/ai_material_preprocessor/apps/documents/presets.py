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
        label="Research Paper",
        description=(
            "Create a traceable AI Context Pack with local OCR when available and a 128K "
            "Context Budget."
        ),
        operation=Operation.DOCUMENT_CONTEXT_PACK,
        context_budget=128000,
        ocr_enabled=True,
    ),
    DocumentPreset(
        preset_id="course_notes",
        label="Course Notes",
        description=(
            "Prepare structured notes as AI-ready Markdown inside upload packs with a 64K "
            "Context Budget."
        ),
        operation=Operation.DOCUMENT_CONTEXT_PACK,
        context_budget=64000,
        ocr_enabled=False,
    ),
    DocumentPreset(
        preset_id="coding_documents",
        label="Coding Documents",
        description=(
            "Preserve fenced code blocks with the existing atomic-block pipeline, disable OCR, "
            "and create 64K upload packs."
        ),
        operation=Operation.DOCUMENT_CONTEXT_PACK,
        context_budget=64000,
        ocr_enabled=False,
    ),
)

PRESET_BY_ID = {preset.preset_id: preset for preset in DOCUMENT_PRESETS}
