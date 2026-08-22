from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from ai_material_preprocessor.application.workspaces import WorkspaceId
from ai_material_preprocessor.gui import MainWindow
from ai_material_preprocessor.models import ToolStatus
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


def _first_run_window() -> MainWindow:
    config = deepcopy(DEFAULT_CONFIG)
    config["app"]["onboarding_completed"] = False
    return MainWindow(config=config, tools=toolset())


def test_first_run_shows_welcome_dialog(qtbot) -> None:
    window = _first_run_window()
    qtbot.addWidget(window)

    window.show_onboarding_if_needed()

    assert hasattr(window, "welcome_dialog")
    assert window.welcome_dialog.isVisible()
    assert not hasattr(window, "onboarding_dialog")


def test_completed_onboarding_skips_welcome(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    config["app"]["onboarding_completed"] = True
    window = MainWindow(config=config, tools=toolset())
    qtbot.addWidget(window)

    window.show_onboarding_if_needed()

    assert not hasattr(window, "welcome_dialog")


def test_welcome_import_documents_switches_to_documents_and_opens_chooser(
    qtbot, monkeypatch
) -> None:
    window = _first_run_window()
    qtbot.addWidget(window)
    calls = []
    monkeypatch.setattr(window.document_workspace, "_choose_files", lambda: calls.append(True))

    window._welcome_import_documents()

    assert window.current_workspace is WorkspaceId.DOCUMENTS
    assert calls == [True]


def test_welcome_view_example_opens_examples_folder(qtbot, monkeypatch) -> None:
    window = _first_run_window()
    qtbot.addWidget(window)
    opened = []
    monkeypatch.setattr(
        "ai_material_preprocessor.gui.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()),
    )

    examples = window._examples_dir()
    assert examples is not None
    window._welcome_view_example()

    assert len(opened) == 1
    assert Path(opened[0]) == examples


def test_welcome_view_example_without_examples_shows_message(qtbot, monkeypatch) -> None:
    window = _first_run_window()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_examples_dir", lambda: None)
    shown = []
    monkeypatch.setattr(
        "ai_material_preprocessor.gui.QMessageBox.information",
        lambda *_args, **_kwargs: shown.append(True),
    )

    window._welcome_view_example()

    assert shown == [True]


def test_welcome_continue_setup_opens_tool_onboarding(qtbot, monkeypatch) -> None:
    window = _first_run_window()
    qtbot.addWidget(window)

    window._show_onboarding()

    assert hasattr(window, "onboarding_dialog")
    assert window.onboarding_dialog.isVisible()
