from __future__ import annotations

from pathlib import Path

from ai_material_preprocessor.ui.welcome_dialog import WelcomeDialog


def test_welcome_dialog_shows_primary_actions(qtbot) -> None:
    dialog = WelcomeDialog(examples_dir=Path("examples"))
    qtbot.addWidget(dialog)

    assert dialog.import_button.text() == "Import documents"
    assert dialog.example_button.isVisibleTo(dialog)
    assert dialog.setup_button.text() == "Continue to setup"
    assert dialog.example_button.isVisibleTo(dialog)
    assert dialog.example_button.isEnabled()


def test_welcome_dialog_hides_example_when_examples_absent(qtbot) -> None:
    dialog = WelcomeDialog(examples_dir=None)
    qtbot.addWidget(dialog)

    assert not dialog.example_button.isVisibleTo(dialog)
    assert dialog.import_button.isVisibleTo(dialog)


def test_welcome_dialog_import_emits_and_accepts(qtbot) -> None:
    dialog = WelcomeDialog(examples_dir=None)
    qtbot.addWidget(dialog)
    received = []
    dialog.import_documents.connect(lambda: received.append(True))

    dialog.import_button.click()

    assert received == [True]
    assert dialog.result() == WelcomeDialog.DialogCode.Accepted


def test_welcome_dialog_view_example_emits_and_accepts(qtbot) -> None:
    dialog = WelcomeDialog(examples_dir=Path("examples"))
    qtbot.addWidget(dialog)
    received = []
    dialog.view_example.connect(lambda: received.append(True))

    dialog.example_button.click()

    assert received == [True]
    assert dialog.result() == WelcomeDialog.DialogCode.Accepted


def test_welcome_dialog_continue_emits_and_accepts(qtbot) -> None:
    dialog = WelcomeDialog(examples_dir=None)
    qtbot.addWidget(dialog)
    received = []
    dialog.continue_setup.connect(lambda: received.append(True))

    dialog.setup_button.click()

    assert received == [True]
    assert dialog.result() == WelcomeDialog.DialogCode.Accepted
