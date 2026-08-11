from copy import deepcopy

from PySide6.QtWidgets import QTableWidget

from ai_material_preprocessor.models import ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.ui.onboarding_dialog import OnboardingDialog
from ai_material_preprocessor.ui.settings_dialog import SettingsDialog


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
    dialog.tool_path_inputs["ffprobe"].setText("D:/工具/ffprobe.exe")

    dialog._save()

    assert saved[0]["app"]["theme"] == "dark"
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

    assert detected_configs[-1]["tools"]["ffmpeg"] == "D:/媒体 工具/ffmpeg.exe"
