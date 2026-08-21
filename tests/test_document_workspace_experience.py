from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt

from ai_material_preprocessor.application.default_preview_registry import (
    build_default_preview_registry,
)
from ai_material_preprocessor.models import Operation, ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.ui.document_mascot import DocumentMascotState
from ai_material_preprocessor.ui.settings_dialog import SettingsDialog
from ai_material_preprocessor.ui.theme import stylesheet_for_theme
from ai_material_preprocessor.ui.workspaces.common import WorkspacePresentationState
from ai_material_preprocessor.ui.workspaces.documents import DocumentWorkspace


def toolset(**available: bool) -> dict[str, ToolStatus]:
    return {
        name: ToolStatus(name, f"C:/tools/{name}.exe" if enabled else None)
        for name, enabled in {
            "markitdown": available.get("markitdown", False),
            "rapidocr": available.get("rapidocr", False),
            "libreoffice": available.get("libreoffice", False),
            "winword": available.get("winword", False),
            "powerpoint": available.get("powerpoint", False),
        }.items()
    }


def workspace(qtbot, **tools: bool) -> DocumentWorkspace:
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(**tools), build_default_preview_registry()
    )
    qtbot.addWidget(view)
    return view


def test_document_empty_state_prioritizes_input_over_options(qtbot) -> None:
    view = workspace(qtbot, markitdown=True)

    assert view.presentation_state is WorkspacePresentationState.EMPTY
    assert view.mascot_view.state is DocumentMascotState.EMPTY
    assert view.empty_guidance.isVisibleTo(view)
    assert not view.preparation_panel.isVisibleTo(view)
    assert view.start_button.text() == "Prepare documents"
    assert not view.start_button.isEnabled()
    assert "PDF" in view.input_description_label.text()


def test_document_input_is_rendered_as_compact_rows_with_type_size_and_path(
    qtbot, tmp_path: Path
) -> None:
    view = workspace(qtbot, markitdown=True)
    first = tmp_path / "很长的中文课程讲义第一章.pdf"
    second = tmp_path / "a-very-long-english-document-name-for-ai-preparation.txt"
    first.write_bytes(b"pdf")
    second.write_bytes(b"notes")

    view.add_inputs([str(first), str(second)])

    assert view.document_list.topLevelItemCount() == 2
    assert view.document_list.headerItem().text(0) == "Document"
    assert view.document_list.headerItem().text(1) == "Type"
    assert view.document_list.headerItem().text(2) == "Size"
    assert view.document_list.topLevelItem(0).toolTip(0)
    assert view.selected_count.text() == "2 documents selected"
    assert view.preparation_panel.isVisibleTo(view)
    assert view.mascot_view.state is DocumentMascotState.READY


def test_document_processing_mode_uses_product_labels_without_changing_operation_data(
    qtbot, tmp_path: Path
) -> None:
    view = workspace(qtbot, markitdown=True)
    source = tmp_path / "lesson.docx"
    source.touch()
    view.add_inputs([str(source)])

    assert view.operation.currentData() == Operation.TO_MARKDOWN.value
    assert view.operation.currentText() == "AI-ready Markdown"
    assert "structure" in view.operation_description.text().lower()
    assert view.start_button.text() == "Prepare documents"


def test_document_advanced_options_are_progressively_disclosed(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True, rapidocr=True)
    source = tmp_path / "lesson.docx"
    source.touch()
    view.add_inputs([str(source)])

    assert not view.advanced_panel.isVisibleTo(view)
    view.advanced_toggle.click()
    assert view.advanced_panel.isVisibleTo(view)
    assert view.target_tokens.isVisibleTo(view)
    view.advanced_toggle.click()
    assert not view.advanced_panel.isVisibleTo(view)


def test_missing_document_tool_is_explained_before_start(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot)
    source = tmp_path / "lesson.txt"
    source.touch()
    view.add_inputs([str(source)])

    assert view.operation.count() == 1
    assert view.operation.currentData() == Operation.TO_MARKDOWN.value
    assert not view.operation.model().item(0).isEnabled()
    assert not view.start_button.isEnabled()
    assert "MarkItDown" in view.tool_hint.text()
    assert view.setup_tool_button.isVisibleTo(view)


def test_document_summary_and_mascot_follow_real_presentation_state(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True)
    source = tmp_path / "lesson.txt"
    source.touch()
    view.add_inputs([str(source)])

    assert "1 document" in view.summary_count.text()
    assert "AI-ready Markdown" in view.summary_mode.text()

    view.set_progress(40, "正在转换 lesson.txt")
    assert view.mascot_view.state is DocumentMascotState.PROCESSING
    assert "40%" in view.state_heading.text()

    view.set_completed([str(tmp_path / "result.md")], ["one warning"])
    assert view.presentation_state is WorkspacePresentationState.WARNING
    assert view.mascot_view.state is DocumentMascotState.WARNING
    assert "1" in view.result_heading.text()
    assert view.result_details.isVisibleTo(view)

    view.set_presentation_state(WorkspacePresentationState.ERROR, "Conversion failed")
    assert view.mascot_view.state is DocumentMascotState.ERROR
    assert "Conversion failed" in view.state_message.text()
    assert view.technical_details_button.isVisibleTo(view)


def test_document_theme_has_explicit_light_and_dark_accessible_states() -> None:
    light = stylesheet_for_theme("light")
    dark = stylesheet_for_theme("dark")

    for selector in (
        "QFrame#documentDropPanel",
        "QFrame#documentSummary",
        "QFrame#documentStateWarning",
        "QFrame#documentMascot",
        "QPushButton#documentPrimary:focus",
        "QTreeWidget#documentList",
    ):
        assert selector in light
        assert selector in dark
    assert light != dark
    assert "#527463" in light
    assert "#8db59f" in dark


def test_document_selection_can_remove_only_selected_rows(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True)
    sources = [tmp_path / "one.txt", tmp_path / "two.txt"]
    for source in sources:
        source.touch()
    view.add_inputs([str(source) for source in sources])
    view.document_list.topLevelItem(0).setSelected(True)

    qtbot.mouseClick(view.remove_button, Qt.MouseButton.LeftButton)

    assert len(view.paths) == 1
    assert view.document_list.topLevelItemCount() == 1


def test_documents_settings_open_on_processing_defaults_and_document_tools(qtbot) -> None:
    dialog = SettingsDialog(
        deepcopy(DEFAULT_CONFIG),
        toolset(),
        save_callback=lambda _: None,
        detector=lambda _: toolset(),
        initial_tab="documents",
    )
    qtbot.addWidget(dialog)

    assert dialog.settings_tabs.currentIndex() == 1
    assert dialog.settings_tabs.tabText(1) == "Documents"
    assert dialog.document_mode.currentData() in {"enhanced", "raw"}
