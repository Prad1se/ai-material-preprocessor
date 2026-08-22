from __future__ import annotations

import webbrowser

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import __version__
from ..services.updates import UpdateCheckResult, UpdateState, check_for_updates
from .window_sizing import fit_dialog_to_available_space


class UpdateCheckThread(QThread):
    completed = Signal(object)

    def __init__(self, enabled: bool, parent=None) -> None:
        super().__init__(parent)
        self.enabled = enabled

    def run(self) -> None:
        self.completed.emit(check_for_updates(current_version=__version__, enabled=self.enabled))


class AboutDialog(QDialog):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.update_thread: UpdateCheckThread | None = None
        self.release_url = ""
        self.setWindowTitle("关于")
        fit_dialog_to_available_space(self, 520, 280, minimum_width=420, minimum_height=240)
        root = QVBoxLayout(self)
        title = QLabel("AI 素材预处理工具")
        title.setObjectName("sectionTitle")
        self.version_label = QLabel(f"版本 {__version__} · Windows 2.0 发布候选版")
        self.version_label.setWordWrap(True)
        self.privacy_label = QLabel(
            "文件默认只在本地处理，不上传源文档、视频、GPS 或历史记录；原文件永不覆盖。"
        )
        self.privacy_label.setWordWrap(True)
        consent = bool(config.get("app", {}).get("update_check_enabled", False))
        self.update_status = QLabel(
            "可以手动检查 GitHub 更新。" if consent else "联网检查默认关闭，请先在设置中授权。"
        )
        self.update_status.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(self.version_label)
        root.addWidget(self.privacy_label)
        root.addSpacing(8)
        root.addWidget(self.update_status)

        actions = QHBoxLayout()
        self.check_updates_button = QPushButton("检查更新")
        self.check_updates_button.setEnabled(consent)
        self.check_updates_button.clicked.connect(self._check_updates)
        self.open_release_button = QPushButton("打开发布页")
        self.open_release_button.setEnabled(False)
        self.open_release_button.clicked.connect(self._open_release)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        actions.addWidget(self.check_updates_button)
        actions.addWidget(self.open_release_button)
        actions.addStretch()
        actions.addWidget(close)
        root.addLayout(actions)

    def _check_updates(self) -> None:
        self.check_updates_button.setEnabled(False)
        self.update_status.setText("正在检查 GitHub Releases…")
        self.update_thread = UpdateCheckThread(True, self)
        self.update_thread.completed.connect(self._update_completed)
        self.update_thread.start()

    def _update_completed(self, result: UpdateCheckResult) -> None:
        self.update_status.setText(result.message)
        self.release_url = result.release_url
        self.open_release_button.setEnabled(
            result.state is UpdateState.AVAILABLE and bool(result.release_url)
        )
        self.check_updates_button.setEnabled(True)

    def _open_release(self) -> None:
        if self.release_url:
            webbrowser.open(self.release_url)
