from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPalette
from PySide6.QtWidgets import QApplication, QFrame

from ai_material_preprocessor.gui import MOUSE_STATE_ASSETS, MainWindow, mouse_asset_path
from ai_material_preprocessor.models import Operation, ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG


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
