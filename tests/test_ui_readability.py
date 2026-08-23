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
    # 深色模式下主按钮与选择文件按钮底色不同，前景色必须分别适配。
    assert "QPushButton#documentPrimary {\n    color: #f8f9fc;\n}" in dark
    assert "QPushButton#documentChooseFiles {\n    color: #17211c;\n}" in dark


def test_dark_button_hover_replaces_light_pink_background() -> None:
    light = stylesheet_for_theme("light")
    dark = stylesheet_for_theme("dark")

    assert "QPushButton:hover { background: #ffe4e8; }" in light
    assert "#ffe4e8" not in dark
    assert "QPushButton:hover { background: #3b292e; }" in dark
    # 主按钮悬停时背景切换为浅绿，前景必须同步换为深色保持对比度。
    assert "QPushButton#documentPrimary:hover {" in dark
    assert "background: #9bc4ad;" in dark
    assert "color: #17211c;" in dark


def _relative_luminance(hex_color: str) -> float:
    def channel(value: str) -> float:
        raw = int(value, 16) / 255
        return raw / 12.92 if raw <= 0.03928 else ((raw + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(hex_color[1:3])
        + 0.7152 * channel(hex_color[3:5])
        + 0.0722 * channel(hex_color[5:7])
    )


def _contrast_ratio(foreground: str, background: str) -> float:
    first = _relative_luminance(foreground)
    second = _relative_luminance(background)
    lighter, darker = (first, second) if first >= second else (second, first)
    return (lighter + 0.05) / (darker + 0.05)


def test_dark_control_states_meet_contrast_requirements() -> None:
    """深色模式 hover/disabled/focus/warning/selected 状态都必须保持可读。"""

    dark = stylesheet_for_theme("dark")

    assert _contrast_ratio("#9a9ca5", "#26272b") >= 4.5  # disabled 按钮文字/背景
    assert (
        "QPushButton:disabled { color: #9a9ca5; background: #26272b; border-color: #5b5c61; }"
        in dark
    )
    assert _contrast_ratio("#f8f9fc", "#8f3348") >= 4.5  # 主按钮文字/深粉背景
    assert _contrast_ratio("#17211c", "#9bc4ad") >= 4.5  # 选择文件按钮文字/浅绿背景
    assert _contrast_ratio("#f5f5f7", "#5a3039") >= 4.5  # 表格选中行
    assert _contrast_ratio("#ffc0ca", "#2b2527") >= 4.5  # 警告提示文字/背景

    assert "QPushButton:focus {\n    border-color: #ff9aaa;\n}" in dark
    assert "QPushButton#primary:focus, QPushButton#documentPrimary:focus" in dark
    assert (
        "QListWidget:focus, QTreeWidget:focus, QPlainTextEdit:focus {\n    border-color: #ff9aaa;\n}"
        in dark
    )
    assert (
        "QTableWidget {\n    selection-background-color: #5a3039;\n    selection-color: #f5f5f7;\n}"
        in dark
    )


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


def test_operation_display_unifies_legacy_values_with_current_labels() -> None:
    from ai_material_preprocessor.models import Operation, operation_display, status_display

    assert operation_display(Operation.TO_MARKDOWN) == "AI 就绪 Markdown"
    assert operation_display(Operation.TO_PDF) == "创建 PDF 副本"
    assert operation_display(Operation.DOCUMENT_CONTEXT_PACK) == "AI 上下文包"
    assert operation_display(Operation.COMPRESS_VIDEO) == "压缩视频"
    # 旧枚举原值（历史记录、持久化数据）映射到同一份统一标签。
    assert operation_display("生成 AI 资料包 / Markdown") == "AI 就绪 Markdown"
    assert operation_display("转为 PDF") == "创建 PDF 副本"
    assert operation_display("未知操作") == "未知操作"
    assert status_display(TaskStatus.SUCCESS) == "成功"
    assert status_display("cancelled") == "已取消"


def test_history_dialog_shares_unified_operation_labels(qtbot, tmp_path) -> None:
    from ai_material_preprocessor.services.history_repository import HistoryRepository
    from ai_material_preprocessor.ui.history_dialog import HistoryDialog

    dialog = HistoryDialog(HistoryRepository(tmp_path / "History"))
    qtbot.addWidget(dialog)

    labels = [
        dialog.operation_filter.itemText(index) for index in range(dialog.operation_filter.count())
    ]
    assert "AI 就绪 Markdown" in labels
    assert "创建 PDF 副本" in labels
    assert "AI 上下文包" in labels
    assert "生成 AI 资料包 / Markdown" not in labels


def test_task_center_and_workspace_share_status_labels(qtbot) -> None:
    from ai_material_preprocessor.ui.task_center_panel import TaskCenterPanel

    panel = TaskCenterPanel()
    qtbot.addWidget(panel)
    panel.upsert("task-1", "文档", "lesson.docx", "AI 就绪 Markdown", TaskStatus.FAILED, 10, "失败")

    assert panel.table.item(0, 3).text() == "失败"
    assert panel.table.item(0, 2).text() == "AI 就绪 Markdown"

    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=_tools(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)
    window.document_workspace.upsert_task(
        "task-2", "lesson.docx", "AI 就绪 Markdown", TaskStatus.RUNNING, 40
    )
    recent = window.document_workspace.recent_tasks
    assert recent.item(0, 1).text() == "AI 就绪 Markdown"
    assert recent.item(0, 2).text() == "运行中"


def test_output_quick_actions_enable_and_copy_path(qtbot, monkeypatch) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=_tools(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)
    workspace = window.video_workspace
    output = "D:/资料/AI素材处理结果/clip.mp4"

    assert not workspace.open_button.isEnabled()
    assert not workspace.reveal_output_button.isEnabled()
    assert not workspace.copy_output_button.isEnabled()

    workspace.set_completed([output], [])
    assert workspace.open_button.isEnabled()
    assert workspace.reveal_output_button.isEnabled()
    assert workspace.copy_output_button.isEnabled()

    captured: list[str] = []

    class FakeClipboard:
        def setText(self, text: str) -> None:
            captured.append(text)

    monkeypatch.setattr(
        "ai_material_preprocessor.ui.workspaces.common.QApplication.clipboard",
        lambda: FakeClipboard(),
    )
    workspace.copy_output_button.click()
    assert captured == [output]


def test_document_workspace_output_quick_actions_enable_after_completion(qtbot) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=_tools(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)
    workspace = window.document_workspace

    assert not workspace.open_button.isEnabled()
    assert not workspace.reveal_output_button.isEnabled()
    assert not workspace.copy_output_button.isEnabled()

    workspace.set_completed(["D:/资料/AI素材处理结果/pack"], [])
    assert workspace.open_button.isEnabled()
    assert workspace.reveal_output_button.isEnabled()
    assert workspace.copy_output_button.isEnabled()


def test_reveal_output_uses_explorer_select_without_shell(qtbot, monkeypatch, tmp_path) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=_tools(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)
    target = tmp_path / "结果.md"
    target.write_text("内容", encoding="utf-8")

    calls: list[tuple[list[str], dict]] = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))

        class FakeHandle:
            pass

        return FakeHandle()

    monkeypatch.setattr("ai_material_preprocessor.gui.subprocess.Popen", fake_popen)
    window._reveal_output(str(target))

    assert calls, "在资源管理器中显示必须触发 explorer /select"
    args, kwargs = calls[0]
    assert args[0] == "explorer"
    assert args[1] == f"/select,{target}"
    assert kwargs.get("shell", None) is False


def test_history_and_task_center_tables_stay_readable_in_narrow_windows(qtbot, tmp_path) -> None:
    from PySide6.QtCore import Qt as QtCore

    from ai_material_preprocessor.services.history_repository import HistoryRepository
    from ai_material_preprocessor.ui.history_dialog import HistoryDialog
    from ai_material_preprocessor.ui.task_center_panel import TaskCenterPanel

    long_name = "非常长的课程资料文件名称" * 12 + ".docx"
    long_message = "这条进度消息特别长，" * 40

    panel = TaskCenterPanel()
    qtbot.addWidget(panel)
    panel.upsert(
        "task-1", "文档", long_name, "AI 就绪 Markdown", TaskStatus.RUNNING, 30, long_message
    )
    assert panel.table.textElideMode() == QtCore.TextElideMode.ElideRight
    assert not panel.table.wordWrap()
    assert panel.table.item(0, 1).toolTip() == long_name
    assert panel.table.item(0, 5).toolTip() == long_message
    assert panel.table.horizontalHeader().minimumSectionSize() <= 56
    assert panel.minimumSizeHint().width() < 720

    dialog = HistoryDialog(HistoryRepository(tmp_path / "History"))
    qtbot.addWidget(dialog)
    assert dialog.table.textElideMode() == QtCore.TextElideMode.ElideRight
    assert not dialog.table.wordWrap()
    assert dialog.table.horizontalHeader().minimumSectionSize() <= 56
    assert dialog.minimumWidth() <= 660


def test_workspace_input_lists_keep_long_paths_readable(qtbot, tmp_path) -> None:
    document = tmp_path / ("很长的文档名称" * 15 + ".pdf")
    document.write_text("内容", encoding="utf-8")
    video = tmp_path / ("很长的视频名称" * 15 + ".mp4")
    video.write_text("内容", encoding="utf-8")

    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=_tools(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)

    window.document_workspace.add_inputs([str(document)])
    tree_item = window.document_workspace.document_list.topLevelItem(0)
    assert tree_item is not None
    assert tree_item.toolTip(0) == str(document)

    window.video_workspace.add_inputs([str(video)])
    list_item = window.video_workspace.file_list.item(0)
    assert list_item is not None
    assert list_item.toolTip() == str(video)
