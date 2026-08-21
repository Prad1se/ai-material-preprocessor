from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QTableWidget

from ai_material_preprocessor.gui import (
    MOUSE_STATE_ASSETS,
    HistoryDialog,
    MainWindow,
    mouse_asset_path,
)
from ai_material_preprocessor.models import Job, Operation, QueuedTask, TaskStatus, ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.services.history_repository import HistoryRepository
from ai_material_preprocessor.services.task_manifest import TaskRecord, write_task_manifest
from ai_material_preprocessor.services.task_repository import PersistentTaskQueue


def toolset(**available: bool) -> dict[str, ToolStatus]:
    names = (
        "markitdown",
        "ffmpeg",
        "ffprobe",
        "exiftool",
        "libreoffice",
        "winword",
        "powerpoint",
        "rapidocr",
    )
    return {
        name: ToolStatus(name, f"C:/tools/{name}.exe" if available.get(name, False) else None)
        for name in names
    }


def combo_operations(workspace) -> list[Operation]:
    return [
        Operation(workspace.operation.itemData(index))
        for index in range(workspace.operation.count())
    ]


def test_mouse_assets_are_packaged_transparent_images() -> None:
    assert set(MOUSE_STATE_ASSETS) == {"idle", "thinking", "working", "success", "error"}
    for filename in set(MOUSE_STATE_ASSETS.values()):
        path = mouse_asset_path(filename)
        image = QImage(str(path))
        assert path.is_file()
        assert not image.isNull()
        assert image.hasAlphaChannel()
        assert image.pixelColor(0, 0).alpha() == 0


def test_window_exposes_mouse_mascot_state_machine(qtbot) -> None:
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset())
    qtbot.addWidget(window)

    video = window.video_workspace
    assert video.mouse_mascot.objectName() == "mouseMascot"
    assert video.mouse_mascot.property("state") == "idle"
    assert video.mouse_mascot.pixmap() is not None
    assert not video.mouse_mascot.pixmap().isNull()

    video.set_mouse_state("thinking")
    assert video.mouse_mascot.property("state") == "thinking"


def test_docx_only_shows_valid_available_operations(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(markitdown=True, winword=True))
    qtbot.addWidget(window)

    workspace = window.document_workspace
    workspace.add_inputs([str(source)])

    assert combo_operations(workspace) == [
        Operation.TO_MARKDOWN,
        Operation.DOCUMENT_CONTEXT_PACK,
        Operation.TO_PDF,
    ]
    assert workspace.start_button.isEnabled()
    assert workspace.document_mode.isVisibleTo(workspace)
    assert workspace.split_document.isVisibleTo(workspace)
    assert workspace.ocr_enabled.isVisibleTo(workspace)
    assert workspace.preview_button.isVisibleTo(workspace)
    assert workspace.preview_button.text() == "预览文档处理方案"


def test_mixed_incompatible_batch_disables_start(qtbot, tmp_path: Path) -> None:
    document = tmp_path / "lesson.docx"
    video = tmp_path / "clip.mp4"
    document.touch()
    video.touch()
    window = MainWindow(
        config=DEFAULT_CONFIG,
        tools=toolset(markitdown=True, winword=True, ffmpeg=True),
        handoff_confirmer=lambda *_: False,
    )
    qtbot.addWidget(window)

    workspace = window.document_workspace
    workspace.add_inputs([str(document), str(video)])

    assert combo_operations(workspace) == [
        Operation.TO_MARKDOWN,
        Operation.DOCUMENT_CONTEXT_PACK,
        Operation.TO_PDF,
    ]
    assert workspace.start_button.isEnabled()
    assert workspace.paths == [document.resolve()]
    assert window.video_workspace.paths == []


def test_video_exposes_all_creation_operations(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mov"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(ffmpeg=True))
    qtbot.addWidget(window)

    workspace = window.video_workspace
    workspace.add_inputs([str(source)])

    assert combo_operations(workspace) == [
        Operation.COMPRESS_VIDEO,
        Operation.EXTRACT_AUDIO,
        Operation.STANDARDIZE_MP4,
        Operation.KEYFRAMES_CONTACT_SHEET,
        Operation.RENAME_VIDEO,
        Operation.ORGANIZE_VIDEO,
    ]


def test_location_and_preview_only_show_for_rename(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(ffmpeg=True))
    qtbot.addWidget(window)
    workspace = window.video_workspace
    workspace.add_inputs([str(source)])

    rename_index = combo_operations(workspace).index(Operation.RENAME_VIDEO)
    workspace.operation.setCurrentIndex(rename_index)

    assert workspace.location.isVisibleTo(workspace)
    assert workspace.preview_button.isVisibleTo(workspace)
    assert workspace.rename_template.isVisibleTo(workspace)
    assert not workspace.audio_format.isVisibleTo(workspace)


def test_organize_video_shows_project_location_and_folder_mode(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(ffmpeg=True))
    qtbot.addWidget(window)
    workspace = window.video_workspace
    workspace.add_inputs([str(source)])

    organize_index = combo_operations(workspace).index(Operation.ORGANIZE_VIDEO)
    workspace.operation.setCurrentIndex(organize_index)

    assert workspace.location.isVisibleTo(workspace)
    assert workspace.project_name.isVisibleTo(workspace)
    assert workspace.organize_mode.isVisibleTo(workspace)
    assert workspace.rename_template.isVisibleTo(workspace)
    assert "原视频不移动" in workspace.output_hint.text()


def test_audio_options_show_for_extract_audio(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(ffmpeg=True))
    qtbot.addWidget(window)
    workspace = window.video_workspace
    workspace.add_inputs([str(source)])

    audio_index = combo_operations(workspace).index(Operation.EXTRACT_AUDIO)
    workspace.operation.setCurrentIndex(audio_index)

    assert workspace.audio_format.isVisibleTo(workspace)
    assert not workspace.quality.isVisibleTo(workspace)


def test_quality_options_show_for_compression(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(ffmpeg=True))
    qtbot.addWidget(window)
    workspace = window.video_workspace
    workspace.add_inputs([str(source)])

    compress_index = combo_operations(workspace).index(Operation.COMPRESS_VIDEO)
    workspace.operation.setCurrentIndex(compress_index)

    assert workspace.quality.isVisibleTo(workspace)
    assert not workspace.audio_format.isVisibleTo(workspace)


def test_raw_document_mode_hides_enhancement_options(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.touch()
    window = MainWindow(
        config=DEFAULT_CONFIG,
        tools=toolset(markitdown=True, rapidocr=True),
    )
    qtbot.addWidget(window)
    workspace = window.document_workspace
    workspace.add_inputs([str(source)])

    workspace.document_mode.setCurrentIndex(1)

    assert workspace.document_mode.isVisibleTo(workspace)
    assert not workspace.split_document.isVisibleTo(workspace)
    assert not workspace.target_tokens.isVisibleTo(workspace)
    assert not workspace.ocr_enabled.isVisibleTo(workspace)


def test_storyboard_operation_shows_keyframe_controls(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(ffmpeg=True))
    qtbot.addWidget(window)
    workspace = window.video_workspace
    workspace.add_inputs([str(source)])

    index = combo_operations(workspace).index(Operation.KEYFRAMES_CONTACT_SHEET)
    workspace.operation.setCurrentIndex(index)

    assert workspace.scene_sensitivity.isVisibleTo(workspace)
    assert workspace.max_keyframes.isVisibleTo(workspace)
    assert not workspace.audio_format.isVisibleTo(workspace)


def test_output_hint_distinguishes_single_file_and_ai_package(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(markitdown=True, winword=True))
    qtbot.addWidget(window)
    workspace = window.document_workspace
    workspace.add_inputs([str(source)])

    workspace.document_mode.setCurrentIndex(0)
    assert "AI 资料包" in workspace.output_hint.text()

    pdf_index = combo_operations(workspace).index(Operation.TO_PDF)
    workspace.operation.setCurrentIndex(pdf_index)
    assert "单个 PDF 文件" in workspace.output_hint.text()


def test_window_exposes_central_history_location(qtbot, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset())
    qtbot.addWidget(window)

    assert str(tmp_path) in window.history_label.toolTip()
    assert window.history_button.text() == "History"
    assert window.findChild(QFrame, "capabilityBar") is None


def test_history_dialog_exposes_application_only_details_action(qtbot, tmp_path: Path) -> None:
    dialog = HistoryDialog(HistoryRepository(tmp_path / "History"))
    qtbot.addWidget(dialog)

    assert dialog.details_button.text() == "查看详情"
    assert not dialog.details_button.isEnabled()


def test_window_exposes_visible_task_center_controls(qtbot) -> None:
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset())
    qtbot.addWidget(window)

    assert isinstance(window.task_table, QTableWidget)
    assert [
        window.task_table.horizontalHeaderItem(index).text()
        for index in range(window.task_table.columnCount())
    ] == ["Workspace", "文件", "操作", "状态", "进度", "详情"]
    assert window.cancel_task_button.text() == "取消所选任务"
    assert window.retry_task_button.text() == "重试失败任务"
    assert not window.cancel_task_button.isEnabled()
    assert not window.retry_task_button.isEnabled()
    assert not window.task_table.verticalHeader().isVisible()


def test_window_restores_interrupted_tasks_for_explicit_retry(qtbot, tmp_path: Path) -> None:
    state = PersistentTaskQueue(tmp_path / "state.json")
    now = datetime(2026, 8, 10, tzinfo=UTC)
    source = tmp_path / "课程 资料.docx"
    source.write_bytes(b"docx")
    state.save(
        [
            QueuedTask(
                "recover-me",
                Job(source, Operation.TO_MARKDOWN, tmp_path / "out"),
                status=TaskStatus.RUNNING,
                progress=42,
                attempts=1,
                created_at=now,
                updated_at=now,
            )
        ]
    )

    window = MainWindow(
        config=DEFAULT_CONFIG,
        tools=toolset(markitdown=True),
        task_repository=state,
    )
    qtbot.addWidget(window)

    assert window.task_table.rowCount() == 1
    assert window.task_table.item(0, 0).text() == "Documents"
    assert window.task_table.item(0, 3).text() == "已中断"
    window.task_table.selectRow(0)
    assert window.retry_task_button.isEnabled()
    assert state.load()[0].status is TaskStatus.INTERRUPTED


def test_history_dialog_searches_and_filters_records(qtbot, tmp_path: Path) -> None:
    history = tmp_path / "History"
    source = tmp_path / "课程资料.docx"
    source.write_bytes(b"docx")
    write_task_manifest(
        history,
        [TaskRecord(source, Operation.TO_MARKDOWN, TaskStatus.SUCCESS)],
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
        task_id="document-task",
    )
    video = tmp_path / "broken.mp4"
    video.write_bytes(b"video")
    write_task_manifest(
        history,
        [TaskRecord(video, Operation.COMPRESS_VIDEO, TaskStatus.FAILED, error="failed")],
        created_at=datetime(2026, 8, 10, 1, tzinfo=UTC),
        task_id="video-task",
    )
    dialog = HistoryDialog(HistoryRepository(history))
    qtbot.addWidget(dialog)

    assert dialog.table.rowCount() == 2
    dialog.search_input.setText("课程")
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "课程资料.docx"
    dialog.search_input.clear()
    failed_index = dialog.status_filter.findData(TaskStatus.FAILED.value)
    dialog.status_filter.setCurrentIndex(failed_index)
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 3).text() == "失败"
    assert dialog.delete_records_button.text() == "删除所选记录"
    assert dialog.delete_caches_button.text() == "删除所选缓存"
    assert dialog.close_button.text() == "关闭"
    assert not dialog.table.verticalHeader().isVisible()
    assert "QComboBox QAbstractItemView" in dialog.styleSheet()


def test_file_rows_and_combo_items_stay_readable_with_dark_system_palette(
    qtbot, tmp_path: Path
) -> None:
    app = QApplication.instance()
    assert app is not None
    original = app.palette()
    dark = QPalette(original)
    dark.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
    dark.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
    app.setPalette(dark)
    try:
        source = tmp_path / "lesson.docx"
        source.touch()
        window = MainWindow(
            config=DEFAULT_CONFIG,
            tools=toolset(markitdown=True, winword=True),
        )
        qtbot.addWidget(window)
        workspace = window.document_workspace
        workspace.add_inputs([str(source)])

        expected = "#f5f5f7" if "background: #202124" in window.styleSheet() else "#171717"
        assert workspace.file_list.palette().color(QPalette.ColorRole.Text).name() == expected
        assert workspace.operation.palette().color(QPalette.ColorRole.Text).name() == expected
        assert (
            workspace.operation.view().palette().color(QPalette.ColorRole.Text).name() == expected
        )
        assert workspace.file_list.item(0).text().endswith("lesson.docx")
    finally:
        app.setPalette(original)


def test_window_exposes_settings_without_capability_bar(qtbot, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    window = MainWindow(config=deepcopy(DEFAULT_CONFIG), tools=toolset())
    qtbot.addWidget(window)

    assert window.settings_button.text() == "Settings"
    assert window.about_button.text() == "About"
    assert window.findChild(QFrame, "capabilityBar") is None


def test_window_expands_dropped_folder_and_keeps_file_rows_visible(qtbot, tmp_path: Path) -> None:
    document = tmp_path / "资料" / "课程.docx"
    video = tmp_path / "视频" / "片段.mp4"
    document.parent.mkdir()
    video.parent.mkdir()
    document.touch()
    video.touch()
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=toolset(markitdown=True, ffmpeg=True),
        handoff_confirmer=lambda *_: False,
    )
    qtbot.addWidget(window)

    window.document_workspace.add_inputs([str(tmp_path)])
    window.video_workspace.add_inputs([str(tmp_path)])

    assert window.document_workspace.paths == [document.resolve()]
    assert window.video_workspace.paths == [video.resolve()]
    assert window.document_workspace.file_list.item(0).text()
    assert window.video_workspace.file_list.item(0).text()


def test_missing_tool_hint_links_to_settings_without_full_capability_bar(
    qtbot, tmp_path: Path
) -> None:
    source = tmp_path / "课件.pdf"
    source.touch()
    window = MainWindow(config=deepcopy(DEFAULT_CONFIG), tools=toolset())
    qtbot.addWidget(window)

    workspace = window.document_workspace
    workspace.add_inputs([str(source)])

    assert workspace.tool_hint.isVisibleTo(workspace)
    assert "MarkItDown" in workspace.tool_hint.text()
    assert window.settings_button.isVisibleTo(window)
    assert window.findChild(QFrame, "capabilityBar") is None


def test_window_uses_configured_dark_theme(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    config["app"]["theme"] = "dark"
    window = MainWindow(config=config, tools=toolset())
    qtbot.addWidget(window)

    assert "background: #202124" in window.styleSheet()


def test_completed_onboarding_is_not_shown(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    config["app"]["onboarding_completed"] = True
    window = MainWindow(config=config, tools=toolset())
    qtbot.addWidget(window)

    window.show_onboarding_if_needed()

    assert not hasattr(window, "onboarding_dialog")


def test_open_output_opens_pack_directory_but_parent_for_files(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    window = MainWindow(config=deepcopy(DEFAULT_CONFIG), tools=toolset())
    qtbot.addWidget(window)
    pack = tmp_path / "Context-Pack"
    pack.mkdir()
    file_output = tmp_path / "result.md"
    file_output.touch()
    opened = []
    monkeypatch.setattr("ai_material_preprocessor.gui.os.startfile", opened.append)

    window._open_output(str(pack))
    window._open_output(str(file_output))

    assert opened == [str(pack), str(tmp_path)]
