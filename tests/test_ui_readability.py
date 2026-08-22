from __future__ import annotations

from copy import deepcopy

from PySide6.QtWidgets import QLabel, QScrollArea, QSplitter

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
