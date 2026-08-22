from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtGui import QStandardItemModel

from ai_material_preprocessor.application.default_preview_registry import (
    build_default_preview_registry,
)
from ai_material_preprocessor.apps.documents.presets import DOCUMENT_PRESETS
from ai_material_preprocessor.models import Operation, ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.ui.workspaces.documents import DocumentWorkspace


def _tools(*, markitdown: bool = True, rapidocr: bool = True) -> dict[str, ToolStatus]:
    return {
        name: ToolStatus(name, f"C:/tools/{name}.exe" if available else None)
        for name, available in {
            "markitdown": markitdown,
            "rapidocr": rapidocr,
            "libreoffice": False,
            "winword": False,
            "powerpoint": False,
        }.items()
    }


def _workspace(qtbot, *, markitdown: bool = True, rapidocr: bool = True) -> DocumentWorkspace:
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG),
        _tools(markitdown=markitdown, rapidocr=rapidocr),
        build_default_preview_registry(),
    )
    qtbot.addWidget(view)
    return view


def _add_text(view: DocumentWorkspace, tmp_path: Path) -> Path:
    source = tmp_path / "notes.txt"
    source.write_text("Notes", encoding="utf-8")
    view.add_inputs([str(source)])
    return source


def _select_preset(view: DocumentWorkspace, preset_id: str) -> None:
    index = view.document_preset.findData(preset_id)
    assert index >= 0
    view.document_preset.setCurrentIndex(index)


def test_document_presets_are_additive_templates_for_real_context_pack_parameters() -> None:
    assert [preset.preset_id for preset in DOCUMENT_PRESETS] == [
        "research_paper",
        "course_notes",
        "coding_documents",
    ]
    assert all(preset.operation is Operation.DOCUMENT_CONTEXT_PACK for preset in DOCUMENT_PRESETS)
    assert [preset.context_budget for preset in DOCUMENT_PRESETS] == [128000, 64000, 64000]
    assert [preset.ocr_enabled for preset in DOCUMENT_PRESETS] == [True, False, False]
    assert "代码块" in DOCUMENT_PRESETS[-1].description


def test_research_paper_preset_updates_visible_job_parameters(qtbot, tmp_path: Path) -> None:
    view = _workspace(qtbot)
    _add_text(view, tmp_path)

    _select_preset(view, "research_paper")

    assert view.operation.currentData() == Operation.DOCUMENT_CONTEXT_PACK.value
    assert view.context_budget.currentData() == 128000
    assert view.ocr_enabled.isChecked()
    assert "128K" in view.preset_note.text()


def test_coding_documents_preset_uses_existing_code_preservation_behavior(
    qtbot, tmp_path: Path
) -> None:
    view = _workspace(qtbot)
    _add_text(view, tmp_path)

    _select_preset(view, "coding_documents")

    assert view.operation.currentData() == Operation.DOCUMENT_CONTEXT_PACK.value
    assert view.context_budget.currentData() == 64000
    assert not view.ocr_enabled.isChecked()
    assert "代码块" in view.preset_note.text()


def test_manual_parameter_change_returns_preset_to_custom(qtbot, tmp_path: Path) -> None:
    view = _workspace(qtbot)
    _add_text(view, tmp_path)
    _select_preset(view, "research_paper")

    view.context_budget.setCurrentIndex(view.context_budget.findData(64000))

    assert view.document_preset.currentData() is None
    assert "当前设置" in view.preset_note.text()


def test_preset_values_are_emitted_through_existing_job_model(qtbot, tmp_path: Path) -> None:
    view = _workspace(qtbot)
    sources = [_add_text(view, tmp_path)]
    second = tmp_path / "second.txt"
    second.write_text("Second", encoding="utf-8")
    view.add_inputs([str(second)])
    _select_preset(view, "research_paper")
    emitted = []
    view.jobs_requested.connect(lambda _workspace, jobs: emitted.extend(jobs))

    view._request_jobs()

    assert len(emitted) == 1
    assert emitted[0].input_sources == tuple(sorted((*sources, second), key=lambda path: str(path)))
    assert emitted[0].context_budget == 128000
    assert emitted[0].context_ocr_enabled is True


def test_research_preset_explains_ocr_degradation_when_tool_is_missing(
    qtbot, tmp_path: Path
) -> None:
    view = _workspace(qtbot, rapidocr=False)
    _add_text(view, tmp_path)

    _select_preset(view, "research_paper")

    assert not view.ocr_enabled.isChecked()
    assert "OCR 不可用" in view.preset_note.text()


def test_context_pack_presets_are_disabled_when_operation_is_unavailable(
    qtbot, tmp_path: Path
) -> None:
    view = _workspace(qtbot, markitdown=False)
    _add_text(view, tmp_path)
    model = view.document_preset.model()
    assert isinstance(model, QStandardItemModel)
    research = model.item(view.document_preset.findData("research_paper"))

    assert not research.isEnabled()
    assert "MarkItDown" in research.toolTip()


def test_presets_do_not_add_config_schema_or_persist_hidden_state(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    before_keys = set(config["document"])
    view = DocumentWorkspace(config, _tools(), build_default_preview_registry())
    qtbot.addWidget(view)

    assert set(view.config["document"]) == before_keys
    assert "preset" not in view.config["document"]
