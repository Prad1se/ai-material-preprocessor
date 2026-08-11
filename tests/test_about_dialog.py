from copy import deepcopy

from ai_material_preprocessor import __version__
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.ui.about_dialog import AboutDialog


def test_about_dialog_shows_version_privacy_and_disabled_update_state(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    config["app"]["update_check_enabled"] = False
    dialog = AboutDialog(config)
    qtbot.addWidget(dialog)

    assert __version__ in dialog.version_label.text()
    assert "本地" in dialog.privacy_label.text()
    assert not dialog.check_updates_button.isEnabled()
    assert "设置" in dialog.update_status.text()


def test_about_dialog_enables_manual_check_after_explicit_consent(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    config["app"]["update_check_enabled"] = True
    dialog = AboutDialog(config)
    qtbot.addWidget(dialog)

    assert dialog.check_updates_button.isEnabled()
