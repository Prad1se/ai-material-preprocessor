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


def combo_operations(window: MainWindow) -> list[Operation]:
    return [
        Operation(window.operation.itemData(index)) for index in range(window.operation.count())
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

    assert window.mouse_mascot.objectName() == "mouseMascot"
    assert window.mouse_mascot.property("state") == "idle"
    assert window.mouse_mascot.pixmap() is not None
    assert not window.mouse_mascot.pixmap().isNull()

    window._set_mouse_state("thinking")
    assert window.mouse_mascot.property("state") == "thinking"


def test_docx_only_shows_valid_available_operations(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(markitdown=True, winword=True))
    qtbot.addWidget(window)

    window._add_files([str(source)])

    assert combo_operations(window) == [Operation.TO_MARKDOWN, Operation.TO_PDF]
    assert window.start_button.isEnabled()
    assert window.document_mode.isVisibleTo(window)
    assert window.split_document.isVisibleTo(window)
    assert window.ocr_enabled.isVisibleTo(window)
    assert window.preview_button.isVisibleTo(window)
    assert window.preview_button.text() == "预览处理方案"


def test_mixed_incompatible_batch_disables_start(qtbot, tmp_path: Path) -> None:
    document = tmp_path / "lesson.docx"
    video = tmp_path / "clip.mp4"
    document.touch()
    video.touch()
    window = MainWindow(
        config=DEFAULT_CONFIG,
        tools=toolset(markitdown=True, winword=True, ffmpeg=True),
    )
    qtbot.addWidget(window)

    window._add_files([str(document), str(video)])

    assert combo_operations(window) == []
    assert not window.start_button.isEnabled()
    assert "没有共同" in window.status.text()


def test_video_exposes_all_creation_operations(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mov"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(ffmpeg=True))
    qtbot.addWidget(window)

    window._add_files([str(source)])

    assert combo_operations(window) == [
        Operation.COMPRESS_VIDEO,
        Operation.EXTRACT_AUDIO,
        Operation.STANDARDIZE_MP4,
        Operation.KEYFRAMES_CONTACT_SHEET,
        Operation.RENAME_VIDEO,
    ]


def test_location_and_preview_only_show_for_rename(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(ffmpeg=True))
    qtbot.addWidget(window)
    window._add_files([str(source)])

    rename_index = combo_operations(window).index(Operation.RENAME_VIDEO)
    window.operation.setCurrentIndex(rename_index)

    assert window.location.isVisibleTo(window)
    assert window.preview_button.isVisibleTo(window)
    assert window.rename_template.isVisibleTo(window)
    assert not window.audio_format.isVisibleTo(window)


def test_audio_options_show_for_extract_audio(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(ffmpeg=True))
    qtbot.addWidget(window)
    window._add_files([str(source)])

    audio_index = combo_operations(window).index(Operation.EXTRACT_AUDIO)
    window.operation.setCurrentIndex(audio_index)

    assert window.audio_format.isVisibleTo(window)
    assert not window.quality.isVisibleTo(window)


def test_quality_options_show_for_compression(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(ffmpeg=True))
    qtbot.addWidget(window)
    window._add_files([str(source)])

    compress_index = combo_operations(window).index(Operation.COMPRESS_VIDEO)
    window.operation.setCurrentIndex(compress_index)

    assert window.quality.isVisibleTo(window)
    assert not window.audio_format.isVisibleTo(window)


def test_raw_document_mode_hides_enhancement_options(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.touch()
    window = MainWindow(
        config=DEFAULT_CONFIG,
        tools=toolset(markitdown=True, rapidocr=True),
    )
    qtbot.addWidget(window)
    window._add_files([str(source)])

    window.document_mode.setCurrentIndex(1)

    assert window.document_mode.isVisibleTo(window)
    assert not window.split_document.isVisibleTo(window)
    assert not window.target_tokens.isVisibleTo(window)
    assert not window.ocr_enabled.isVisibleTo(window)


def test_storyboard_operation_shows_keyframe_controls(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(ffmpeg=True))
    qtbot.addWidget(window)
    window._add_files([str(source)])

    index = combo_operations(window).index(Operation.KEYFRAMES_CONTACT_SHEET)
    window.operation.setCurrentIndex(index)

    assert window.scene_sensitivity.isVisibleTo(window)
    assert window.max_keyframes.isVisibleTo(window)
    assert not window.audio_format.isVisibleTo(window)


def test_output_hint_distinguishes_single_file_and_ai_package(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.touch()
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset(markitdown=True, winword=True))
    qtbot.addWidget(window)
    window._add_files([str(source)])

    window.document_mode.setCurrentIndex(0)
    assert "AI 资料包" in window.output_hint.text()

    pdf_index = combo_operations(window).index(Operation.TO_PDF)
    window.operation.setCurrentIndex(pdf_index)
    assert "单个 PDF 文件" in window.output_hint.text()


def test_window_exposes_central_history_location(qtbot, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    window = MainWindow(config=DEFAULT_CONFIG, tools=toolset())
    qtbot.addWidget(window)

    assert str(tmp_path) in window.history_label.toolTip()
    assert window.history_button.text() == "查看历史记录"
    assert window.clear_history_button.text() == "清除历史"
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
    ] == ["文件", "操作", "状态", "进度", "详情"]
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
    assert window.task_table.item(0, 2).text() == "已中断"
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
        window._add_files([str(source)])
        window.show()
        app.processEvents()

        expected = "#171717"
        assert window.file_list.palette().color(QPalette.ColorRole.Text).name() == expected
        assert window.operation.palette().color(QPalette.ColorRole.Text).name() == expected
        assert window.operation.view().palette().color(QPalette.ColorRole.Text).name() == expected
        assert window.file_list.item(0).text().endswith("lesson.docx")
    finally:
        app.setPalette(original)
