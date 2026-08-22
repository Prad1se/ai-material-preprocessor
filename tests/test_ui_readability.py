from __future__ import annotations

from copy import deepcopy

from PySide6.QtWidgets import QApplication, QBoxLayout, QLabel, QScrollArea, QSplitter

from ai_material_preprocessor.gui import MainWindow
from ai_material_preprocessor.models import ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.services.source_map import (
    SourceLocation,
    SourceMap,
    SourceMapEntry,
    SourceMapSource,
)
from ai_material_preprocessor.ui.preview_dialog import DocumentReportDialog
from ai_material_preprocessor.ui.settings_dialog import SettingsDialog
from ai_material_preprocessor.ui.source_map_view import SourceMapView
from ai_material_preprocessor.ui.theme import stylesheet_for_theme
from ai_material_preprocessor.ui.window_sizing import fit_dialog_to_available_space


def _tools() -> dict[str, ToolStatus]:
    return {name: ToolStatus(name, None) for name in ("markitdown", "ffmpeg")}


def test_document_and_video_settings_pages_have_outer_scroll_area(qtbot) -> None:
    dialog = SettingsDialog(
        deepcopy(DEFAULT_CONFIG),
        _tools(),
        save_callback=lambda _: None,
        detector=lambda _: _tools(),
    )
    qtbot.addWidget(dialog)

    assert isinstance(dialog.tool_path_scroll, QScrollArea)
    assert isinstance(dialog.video_tool_path_scroll, QScrollArea)
    assert dialog.tool_path_scroll.widgetResizable()
    assert dialog.video_tool_path_scroll.widgetResizable()


def test_preview_output_path_is_wrapped_instead_of_forcing_dialog_width(qtbot) -> None:
    long_path = "D:/资料/" + "非常长的中文目录/" * 20 + "Context-Pack"
    dialog = DocumentReportDialog(
        [{"source": "课程.pdf", "parameters": {"输出": long_path}}], [long_path]
    )
    qtbot.addWidget(dialog)

    output_labels = [label for label in dialog.findChildren(QLabel) if long_path in label.text()]
    assert output_labels
    assert all(label.wordWrap() for label in output_labels)


def test_source_map_uses_collapsible_splitter_and_localized_location(qtbot) -> None:
    view = SourceMapView()
    qtbot.addWidget(view)
    location = SourceLocation("page", "第 37 页", "PDF page 37", 37, None, False)
    source = SourceMapSource("source-001", 1, "课程.pdf", ".pdf", "page", None)
    entry = SourceMapEntry(
        "block-001",
        "source-001",
        1,
        1,
        (),
        12,
        True,
        "内容",
        "a" * 64,
        True,
        (location,),
        location,
    )
    view.set_source_map(SourceMap(1, (source,), (entry,), True))

    splitters = view.findChildren(QSplitter)
    assert splitters and splitters[0].childrenCollapsible()
    assert view.card_location_value.text() == "第 37 页"


def test_dark_primary_color_is_dark_enough_for_light_foreground() -> None:
    dark = stylesheet_for_theme("dark")
    assert "background: #8f3348" in dark
    assert "QPushButton#documentChooseFiles, QPushButton#documentPrimary" in dark
    assert "color: #17211c" in dark


def test_shell_compacts_navigation_for_small_windows(qtbot) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=_tools(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)

    window.resize(760, 600)
    window.show()
    QApplication.processEvents()

    assert window.minimumWidth() <= 760
    assert window.navigation.width() <= 150
    assert window.document_workspace.width() >= 600

    window.resize(900, 680)
    QApplication.processEvents()
    assert window.navigation.width() == 180
    assert window.document_workspace.mascot_view.isVisibleTo(window.document_workspace)

    window.resize(1180, 760)
    QApplication.processEvents()
    assert window.navigation.width() == 218


def test_document_workspace_hides_mascot_without_horizontal_overflow(qtbot) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=_tools(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)
    window.resize(760, 600)
    window.show()
    QApplication.processEvents()

    workspace = window.document_workspace
    scroll = workspace.content_stack.widget(0)
    assert not workspace.mascot_view.isVisibleTo(workspace)
    assert scroll.horizontalScrollBar().maximum() == 0


def test_video_workspace_stacks_panels_at_small_width(qtbot) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=_tools(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)
    window.resize(760, 600)
    window.show()
    window.video_workspace.show()
    QApplication.processEvents()

    assert window.video_workspace.content_layout.direction() is QBoxLayout.Direction.TopToBottom


def test_settings_dialog_accepts_small_window_with_scrollable_general_page(qtbot) -> None:
    dialog = SettingsDialog(
        deepcopy(DEFAULT_CONFIG),
        _tools(),
        save_callback=lambda _: None,
        detector=lambda _: _tools(),
    )
    qtbot.addWidget(dialog)

    dialog.resize(640, 500)
    dialog.show()
    QApplication.processEvents()

    assert dialog.minimumWidth() <= 640
    assert dialog.minimumHeight() <= 500
    assert isinstance(dialog.general_scroll, QScrollArea)
    assert dialog.general_scroll.widgetResizable()


def test_dialog_size_is_bounded_by_small_parent_window(qtbot) -> None:
    from PySide6.QtWidgets import QDialog, QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(760, 600)
    dialog = QDialog(parent)
    qtbot.addWidget(dialog)

    fit_dialog_to_available_space(dialog, 1120, 720, minimum_width=640, minimum_height=420)

    assert dialog.width() == 728
    assert dialog.height() == 568
