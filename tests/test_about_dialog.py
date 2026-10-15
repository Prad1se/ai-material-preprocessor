from copy import deepcopy
from threading import Event

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPushButton

from ai_material_preprocessor import __version__
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.ui.about_dialog import AboutDialog
from ai_material_preprocessor.ui.theme import stylesheet_for_theme


def test_about_dialog_shows_version_privacy_and_disabled_update_state(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    config["app"]["update_check_enabled"] = False
    dialog = AboutDialog(config)
    qtbot.addWidget(dialog)

    assert __version__ in dialog.version_label.text()
    assert "本地" in dialog.privacy_label.text()
    assert not dialog.check_updates_button.isEnabled()
    assert "设置" in dialog.update_status.text()
    assert dialog.run_diagnostics_button.text() == "运行本地诊断"


def test_about_dialog_enables_manual_check_after_explicit_consent(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    config["app"]["update_check_enabled"] = True
    dialog = AboutDialog(config)
    qtbot.addWidget(dialog)

    assert dialog.check_updates_button.isEnabled()


def test_about_dialog_close_discards_pending_update_check(qtbot, monkeypatch) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    config["app"]["update_check_enabled"] = True
    started = Event()
    release = Event()

    def check(*, current_version: str, enabled: bool):
        del current_version, enabled
        started.set()
        assert release.wait(1)
        from ai_material_preprocessor.services.updates import UpdateCheckResult, UpdateState

        return UpdateCheckResult(UpdateState.UP_TO_DATE, "当前已经是可用的最新版本。")

    monkeypatch.setattr("ai_material_preprocessor.ui.about_dialog.check_for_updates", check)
    dialog = AboutDialog(config)
    qtbot.addWidget(dialog)

    dialog._check_updates()
    qtbot.waitUntil(started.is_set)
    dialog.accept()
    release.set()
    qtbot.wait(50)

    assert dialog.update_thread is None
    assert dialog.update_status.text() == "正在检查 GitHub Releases…"


def test_about_dialog_keeps_150_percent_action_labels_unclipped(qtbot) -> None:
    dialog = AboutDialog(deepcopy(DEFAULT_CONFIG))
    qtbot.addWidget(dialog)
    dialog.setStyleSheet(stylesheet_for_theme("light"))
    enlarged_font = QFont(dialog.font())
    enlarged_font.setPointSizeF(dialog.font().pointSizeF() * 1.5)
    for button in dialog.findChildren(QPushButton):
        button.setFont(enlarged_font)

    buttons = dialog.findChildren(QPushButton)
    actions = dialog.layout().itemAt(dialog.layout().count() - 1).layout()
    assert actions is not None
    margins = dialog.layout().contentsMargins()
    required_width = sum(button.sizeHint().width() for button in buttons) + actions.spacing() * 3
    assert dialog.minimumWidth() >= 520
    assert required_width <= dialog.minimumWidth() - margins.left() - margins.right()
