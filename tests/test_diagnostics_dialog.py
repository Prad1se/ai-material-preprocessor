from copy import deepcopy
from pathlib import Path
from threading import Event

from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.ui.diagnostics_dialog import DiagnosticsDialog


def test_diagnostics_dialog_runs_report_and_exposes_local_report_path(
    qtbot, tmp_path: Path
) -> None:
    report = tmp_path / "diagnostics.json"
    report.write_text("{}\n", encoding="utf-8")
    calls: list[tuple[Path, dict]] = []

    def runner(output: Path, *, config: dict) -> Path:
        calls.append((output, config))
        return report

    dialog = DiagnosticsDialog(deepcopy(DEFAULT_CONFIG), runner=runner)
    qtbot.addWidget(dialog)
    dialog.run_button.click()
    qtbot.waitUntil(lambda: dialog.report_path == report)

    assert calls
    assert "已导出" in dialog.status_label.text()
    assert dialog.report_path == report
    assert dialog.open_button.isEnabled()


def test_diagnostics_dialog_runs_self_test_off_the_ui_thread(qtbot, tmp_path: Path) -> None:
    started = Event()
    release = Event()
    report = tmp_path / "diagnostics.json"

    def runner(_output: Path, *, config: dict) -> Path:
        del config
        started.set()
        assert release.wait(1)
        report.write_text("{}\n", encoding="utf-8")
        return report

    dialog = DiagnosticsDialog(deepcopy(DEFAULT_CONFIG), runner=runner)
    qtbot.addWidget(dialog)
    dialog.run_button.click()
    qtbot.waitUntil(started.is_set)

    assert not dialog.run_button.isEnabled()
    release.set()
    qtbot.waitUntil(lambda: dialog.report_path == report)
