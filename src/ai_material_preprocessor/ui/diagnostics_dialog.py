from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..diagnostics import default_diagnostic_report_directory, run_self_test
from .background_tasks import BackgroundCall, start_background_call
from .window_sizing import fit_dialog_to_available_space

DiagnosticRunner = Callable[..., Path]


class DiagnosticsDialog(QDialog):
    """Manual local-only support diagnostic entry point."""

    def __init__(
        self, config: dict, parent=None, *, runner: DiagnosticRunner = run_self_test
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.runner = runner
        self.report_path: Path | None = None
        self._worker: BackgroundCall | None = None
        self.setWindowTitle("本地诊断")
        fit_dialog_to_available_space(self, 500, 240, minimum_width=400, minimum_height=210)

        root = QVBoxLayout(self)
        title = QLabel("运行本地诊断")
        title.setObjectName("sectionTitle")
        self.description = QLabel(
            "仅检测本机工具与处理能力。报告不包含源文件路径、文档内容、GPS 或配置内容。"
        )
        self.description.setWordWrap(True)
        self.status_label = QLabel("尚未运行。")
        self.status_label.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(self.description)
        root.addSpacing(8)
        root.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.run_button = QPushButton("运行并导出")
        self.run_button.clicked.connect(self._run)
        self.open_button = QPushButton("打开报告位置")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_report_location)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        actions.addWidget(self.run_button)
        actions.addWidget(self.open_button)
        actions.addStretch()
        actions.addWidget(close)
        root.addLayout(actions)

    def _run(self) -> None:
        if self._worker is not None:
            return
        self.run_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.status_label.setText("正在运行本地诊断…")
        runner = self.runner
        config = copy.deepcopy(self.config)
        worker = BackgroundCall(
            lambda: runner(default_diagnostic_report_directory(), config=config)
        )
        self._worker = worker
        worker.succeeded.connect(self._succeeded)
        worker.failed.connect(self._failed)
        start_background_call(worker)

    def _succeeded(self, raw_path: object) -> None:
        if self.sender() is not self._worker or not isinstance(raw_path, Path):
            return
        self._worker = None
        self.report_path = raw_path
        self.status_label.setText("已导出本地诊断报告。")
        self.run_button.setEnabled(True)
        self.open_button.setEnabled(True)

    def _failed(self, _message: str) -> None:
        if self.sender() is not self._worker:
            return
        self._worker = None
        self.status_label.setText("诊断未完成；可重试。报告不会包含你的文件内容。")
        self.run_button.setEnabled(True)

    def _open_report_location(self) -> None:
        if self.report_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.report_path.parent)))

    def event(self, event: QEvent) -> bool:
        if event.type() is QEvent.Type.Close:
            self._cancel_worker()
        return super().event(event)

    def reject(self) -> None:
        self._cancel_worker()
        super().reject()

    def _cancel_worker(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
