from copy import deepcopy
from pathlib import Path
from threading import Event

from PySide6.QtWidgets import QMessageBox, QPushButton, QTableWidget, QWidget

from ai_material_preprocessor.models import ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.services.tool_installer import ToolInstallResult
from ai_material_preprocessor.ui.onboarding_dialog import OnboardingDialog
from ai_material_preprocessor.ui.settings_dialog import SettingsDialog
from ai_material_preprocessor.ui.tool_installation import ToolInstallationCoordinator


def toolset() -> dict[str, ToolStatus]:
    return {
        "markitdown": ToolStatus("markitdown", "Python API", version="0.1.6"),
        "ffmpeg": ToolStatus("ffmpeg", "D:/tools/ffmpeg.exe", version="7.1"),
        "ffprobe": ToolStatus("ffprobe", None),
        "exiftool": ToolStatus("exiftool", None),
        "libreoffice": ToolStatus("libreoffice", None),
        "winword": ToolStatus("winword", "C:/Office/WINWORD.EXE"),
        "powerpoint": ToolStatus("powerpoint", "C:/Office/POWERPNT.EXE"),
        "rapidocr": ToolStatus("rapidocr", None),
    }


def test_onboarding_has_mouse_welcome_privacy_and_tool_detection(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    dialog = OnboardingDialog(config, toolset(), save_callback=lambda _: None)
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "欢迎使用 AI 素材预处理工具"
    assert dialog.mouse_mascot.pixmap() is not None
    assert "本机" in dialog.privacy_text.text()
    assert isinstance(dialog.tool_table, QTableWidget)
    assert dialog.tool_table.rowCount() == 8
    assert dialog.redetect_button.text() == "重新检测"
    exiftool_action = dialog.tool_table.action_button("exiftool")
    libreoffice_action = dialog.tool_table.action_button("libreoffice")
    assert isinstance(exiftool_action, QPushButton)
    assert exiftool_action.text() == "一键补充"
    assert isinstance(libreoffice_action, QPushButton)
    assert libreoffice_action.text() == "通过 WinGet 安装"


def test_onboarding_tool_table_fits_medium_window_without_clipping(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    dialog = OnboardingDialog(config, toolset(), save_callback=lambda _: None)
    qtbot.addWidget(dialog)
    dialog.resize(860, 680)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)

    table = dialog.tool_table
    assert table.horizontalScrollBar().maximum() == 0
    assert table.visualItemRect(table.item(0, 0)).left() >= 0
    for key in ("ffprobe", "exiftool", "libreoffice"):
        button = table.action_button(key)
        assert button is not None
        assert button.width() >= button.sizeHint().width()


def test_onboarding_tool_table_keeps_primary_columns_in_small_window(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    dialog = OnboardingDialog(config, toolset(), save_callback=lambda _: None)
    qtbot.addWidget(dialog)
    dialog.resize(640, 500)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)

    table = dialog.tool_table
    qtbot.waitUntil(lambda: table.minimumHeight() == 120)
    assert not table.isColumnHidden(0)
    assert not table.isColumnHidden(1)
    assert table.isColumnHidden(2)
    assert table.isColumnHidden(3)
    assert not table.isColumnHidden(4)
    assert not table.isColumnHidden(5)
    assert table.horizontalScrollBar().maximum() == 0
    qtbot.waitUntil(lambda: table.geometry().bottom() < dialog.redetect_button.geometry().top())
    assert dialog.redetect_button.geometry().bottom() <= dialog.contentsRect().bottom()


def test_onboarding_finish_persists_completion(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    saved: list[dict] = []
    dialog = OnboardingDialog(config, toolset(), save_callback=lambda value: saved.append(value))
    qtbot.addWidget(dialog)

    dialog._finish()

    assert saved[0]["app"]["onboarding_completed"] is True


def test_settings_saves_theme_and_custom_tool_paths(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    saved: list[dict] = []
    dialog = SettingsDialog(
        config,
        toolset(),
        save_callback=lambda value: saved.append(value),
        detector=lambda value: toolset(),
    )
    qtbot.addWidget(dialog)
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
    dialog.update_check_enabled.setChecked(True)
    dialog.tool_install_directory.setText("D:/Codex-workspace/managed tools")
    dialog.tool_path_inputs["ffprobe"].setText("D:/工具/ffprobe.exe")

    dialog._save()
    qtbot.waitUntil(lambda: dialog.result() == dialog.DialogCode.Accepted)

    assert saved[0]["app"]["theme"] == "dark"
    assert saved[0]["app"]["update_check_enabled"] is True
    assert saved[0]["tool_management"]["install_directory"] == ("D:/Codex-workspace/managed tools")
    assert saved[0]["tools"]["ffprobe"] == "D:/工具/ffprobe.exe"
    assert dialog.tool_path_scroll.widgetResizable()


def test_settings_redetect_uses_unsaved_custom_paths(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    detected_configs: list[dict] = []

    def detector(value: dict) -> dict[str, ToolStatus]:
        detected_configs.append(value)
        return toolset()

    dialog = SettingsDialog(config, toolset(), detector=detector)
    qtbot.addWidget(dialog)
    dialog.tool_path_inputs["ffmpeg"].setText("D:/媒体 工具/ffmpeg.exe")

    dialog._redetect()
    qtbot.waitUntil(lambda: bool(detected_configs))

    assert detected_configs[-1]["tools"]["ffmpeg"] == "D:/媒体 工具/ffmpeg.exe"


def test_settings_redetect_runs_detector_off_the_ui_thread(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    started = Event()
    release = Event()

    def detector(_: dict) -> dict[str, ToolStatus]:
        started.set()
        assert release.wait(1)
        return toolset()

    dialog = SettingsDialog(config, toolset(), detector=detector)
    qtbot.addWidget(dialog)

    dialog._redetect()
    qtbot.waitUntil(started.is_set)

    assert not dialog.redetect_buttons[0].isEnabled()
    release.set()
    qtbot.waitUntil(lambda: dialog.redetect_buttons[0].isEnabled())


def test_onboarding_redetect_runs_detector_off_the_ui_thread(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    started = Event()
    release = Event()

    def detector(_: dict) -> dict[str, ToolStatus]:
        started.set()
        assert release.wait(1)
        return toolset()

    dialog = OnboardingDialog(config, toolset(), detector=detector)
    qtbot.addWidget(dialog)

    dialog._redetect()
    qtbot.waitUntil(started.is_set)

    assert not dialog.redetect_button.isEnabled()
    release.set()
    qtbot.waitUntil(dialog.redetect_button.isEnabled)


def test_settings_cancel_discards_pending_tool_detection(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    started = Event()
    release = Event()
    updated = toolset()
    updated["ffmpeg"] = ToolStatus("ffmpeg", None)

    def detector(_: dict) -> dict[str, ToolStatus]:
        started.set()
        assert release.wait(1)
        return updated

    dialog = SettingsDialog(config, toolset(), detector=detector)
    qtbot.addWidget(dialog)

    dialog._redetect()
    qtbot.waitUntil(started.is_set)
    dialog.reject()
    release.set()
    qtbot.wait(50)

    assert dialog._detection is None
    assert dialog.tools["ffmpeg"].available


def test_installed_tool_detection_runs_in_background(qtbot, monkeypatch, tmp_path: Path) -> None:
    started = Event()
    release = Event()
    parent = QWidget()
    qtbot.addWidget(parent)
    changed: list[dict[str, ToolStatus]] = []

    def detector(_: dict) -> dict[str, ToolStatus]:
        started.set()
        assert release.wait(1)
        return toolset()

    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    coordinator = ToolInstallationCoordinator(
        parent,
        deepcopy(DEFAULT_CONFIG),
        save_callback=lambda _: None,
        detector=detector,
        changed_callback=lambda _config, tools: changed.append(tools),
    )

    executable = tmp_path / "exiftool.exe"
    coordinator._succeeded(
        ToolInstallResult("exiftool", "13.59", executable, {"exiftool": executable})
    )
    qtbot.waitUntil(started.is_set)

    assert not changed
    release.set()
    qtbot.waitUntil(lambda: bool(changed))
    assert changed[0]["ffmpeg"].available
