import argparse
import json
import sys
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from .diagnostics import run_self_test
from .gui import MainWindow
from .services.config import load_config
from .services.startup_maintenance import perform_startup_maintenance
from .services.task_repository import PersistentTaskQueue, resolve_task_queue_path


def configure_high_dpi() -> None:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", metavar="OUTPUT_DIRECTORY")
    parser.add_argument("--skip-onboarding", action="store_true")
    args, qt_args = parser.parse_known_args(sys.argv[1:])
    if args.self_test:
        report = run_self_test(Path(args.self_test))
        result = json.loads(report.read_text(encoding="utf-8"))
        return 0 if result["overall"] == "passed" else 1

    configure_high_dpi()
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("AI 素材预处理工具")
    app.setOrganizationName("AI Material Preprocessor")
    config = load_config()
    with suppress(OSError):
        perform_startup_maintenance(config)
    task_repository = PersistentTaskQueue(resolve_task_queue_path(config))
    window = MainWindow(config=config, task_repository=task_repository)
    window.show()
    if not args.skip_onboarding:
        QTimer.singleShot(0, window.show_onboarding_if_needed)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
