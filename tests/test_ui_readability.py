from __future__ import annotations

from copy import deepcopy

from PySide6.QtWidgets import QApplication, QBoxLayout, QLabel, QScrollArea, QSplitter

from ai_material_preprocessor.application.workspaces import WorkspaceId
from ai_material_preprocessor.gui import MainWindow
from ai_material_preprocessor.models import TaskStatus, ToolStatus
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


def test_dark_button_hover_replaces_light_pink_background() -> None:
    light = stylesheet_for_theme("light")
    dark = stylesheet_for_theme("dark")

    assert "QPushButton:hover { background: #ffe4e8; }" in light
    assert "#ffe4e8" not in dark
    assert "QPushButton:hover { background: #3b292e; }" in dark


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


def test_stale_workspace_strings_do_not_break_shell(qtbot, monkeypatch) -> None:
    """旧配置或异常来源可能给出无法识别的工作区字符串，外壳必须兜底而不是崩溃。"""

    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=_tools(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)
    assert window.current_workspace is WorkspaceId.DOCUMENTS

    window.switch_workspace("stale-value")
    assert window.current_workspace is WorkspaceId.DOCUMENTS

    opened: list[WorkspaceId | None] = []
    monkeypatch.setattr(window, "_open_history", opened.append)
    window.document_workspace.history_requested.emit("stale-value")
    window.video_workspace.history_requested.emit("video")
    assert opened == [None, WorkspaceId.VIDEO]


def test_open_output_survives_startfile_failure(qtbot, monkeypatch, tmp_path) -> None:
    """系统拒绝打开文件夹时必须给出可见反馈，槽函数不允许向外抛异常。"""

    from ai_material_preprocessor.services.history_repository import HistoryRepository
    from ai_material_preprocessor.ui.history_dialog import HistoryDialog

    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=_tools(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)
    dialog = HistoryDialog(HistoryRepository(tmp_path / "History"))
    qtbot.addWidget(dialog)

    warnings: list[tuple[str, str]] = []

    def fake_warning(parent, title, text, *args, **kwargs):
        warnings.append((title, text))
        return None

    def exploding_startfile(path):
        raise OSError("shell refused")

    monkeypatch.setattr("ai_material_preprocessor.gui.os.startfile", exploding_startfile)
    monkeypatch.setattr("ai_material_preprocessor.gui.QMessageBox.warning", fake_warning)

    window._open_output("Z:/不存在/结果.md")
    dialog._open_folder()

    assert len(warnings) == 2
    assert all("无法打开" in title for title, _text in warnings)


def test_recent_task_rows_localize_status_labels(qtbot) -> None:
    """最近任务表的状态列与任务中心共用同一份中文标签，不再直出英文枚举原值。"""

    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=_tools(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)

    window.document_workspace.upsert_task(
        "task-1", "lesson.docx", "生成 AI 资料包 / Markdown", TaskStatus.SUCCESS, 100
    )
    window.video_workspace.upsert_task("task-2", "clip.mp4", "压缩视频", TaskStatus.CANCELLED, 40)

    document_table = window.document_workspace.recent_tasks
    video_table = window.video_workspace.recent_tasks
    assert document_table.item(0, 2).text() == "成功"
    assert video_table.item(0, 2).text() == "已取消"
