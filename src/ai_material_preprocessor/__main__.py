import argparse
import json
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .gui import MainWindow
from .diagnostics import run_self_test


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", metavar="OUTPUT_DIRECTORY")
    args, qt_args = parser.parse_known_args(sys.argv[1:])
    if args.self_test:
        report = run_self_test(Path(args.self_test))
        result = json.loads(report.read_text(encoding="utf-8"))
        return 0 if result["overall"] == "passed" else 1

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("AI 素材预处理工具")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
