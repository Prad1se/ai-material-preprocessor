from __future__ import annotations

import copy
from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QWidget

from ..infrastructure.processes import CancellationToken
from ..models import ToolStatus
from ..services.config import save_config
from ..services.tool_installer import (
    DEFAULT_TOOL_SPECS,
    ToolInstaller,
    ToolInstallResult,
    configured_tool_install_root,
)
from ..services.tool_versions import detect_tools_with_versions

ConfigSaver = Callable[[dict], object]
ToolDetector = Callable[[dict], dict[str, ToolStatus]]
ChangedCallback = Callable[[dict, dict[str, ToolStatus]], None]


def apply_install_result(config: dict, result: ToolInstallResult) -> dict:
    candidate = copy.deepcopy(config)
    for key, path in result.tool_paths.items():
        if key in candidate["tools"]:
            candidate["tools"][key] = str(path)
    return candidate


class ToolInstallWorker(QThread):
    progress_changed = Signal(int)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, key: str, install_root, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.install_root = install_root
        self.cancellation = CancellationToken()

    def cancel_install(self) -> None:
        self.cancellation.cancel()

    def run(self) -> None:
        try:
            result = ToolInstaller(install_root=self.install_root).install(
                self.key,
                cancellation=self.cancellation,
                on_progress=self.progress_changed.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)


class ToolInstallationCoordinator(QObject):
    def __init__(
        self,
        parent: QWidget,
        config: dict,
        *,
        save_callback: ConfigSaver = save_config,
        detector: ToolDetector = detect_tools_with_versions,
        changed_callback: ChangedCallback,
    ) -> None:
        super().__init__(parent)
        self.parent_widget = parent
        self.config = copy.deepcopy(config)
        self.save_callback = save_callback
        self.detector = detector
        self.changed_callback = changed_callback
        self.worker: ToolInstallWorker | None = None
        self.progress_dialog: QProgressDialog | None = None

    def update_config(self, config: dict) -> None:
        self.config = copy.deepcopy(config)

    def request(self, key: str) -> None:
        if self.worker is not None:
            QMessageBox.information(self.parent_widget, "正在补充工具", "请等待当前操作完成。")
            return
        spec = DEFAULT_TOOL_SPECS[key]
        install_root = configured_tool_install_root(self.config)
        answer = QMessageBox.question(
            self.parent_widget,
            f"补充 {spec.display_name}？",
            f"用途：{spec.description}\n\n"
            f"来源：{spec.source_url}\n"
            f"版本：{spec.version}\n"
            f"许可证：{spec.license_name}\n"
            f"保存位置：{install_root}\n\n"
            "继续表示允许本次联网下载。WinGet 或安装程序可能显示 Windows 授权窗口。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.progress_dialog = QProgressDialog(
            f"正在补充 {spec.display_name}…",
            "取消",
            0,
            100,
            self.parent_widget,
        )
        self.progress_dialog.setWindowTitle("补充本机能力")
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        self.worker = ToolInstallWorker(key, install_root, self)
        self.progress_dialog.canceled.connect(self.worker.cancel_install)
        self.worker.progress_changed.connect(self.progress_dialog.setValue)
        self.worker.succeeded.connect(self._succeeded)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _succeeded(self, raw_result: object) -> None:
        if not isinstance(raw_result, ToolInstallResult):
            self._failed("工具返回了无法识别的安装结果。")
            return
        candidate = apply_install_result(self.config, raw_result)
        try:
            self.save_callback(candidate)
            tools = self.detector(candidate)
        except OSError as exc:
            self._failed(f"工具已补充，但保存设置失败：{exc}")
            return
        self.config = candidate
        self.changed_callback(copy.deepcopy(candidate), dict(tools))
        if self.progress_dialog is not None:
            self.progress_dialog.setValue(100)
        restart_note = ""
        if raw_result.restart_required:
            restart_note = (
                "\n\nWindows 安装程序要求重启。请保存工作并在方便时重启电脑，然后重新检测。"
            )
        QMessageBox.information(
            self.parent_widget,
            "本机能力已更新",
            "工具补充完成，能力列表已重新检测。" + restart_note,
        )

    def _failed(self, message: str) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.close()
        QMessageBox.critical(
            self.parent_widget,
            "工具补充失败",
            message or "工具补充未完成，请检查网络和安装权限后重试。",
        )

    def _worker_finished(self) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.close()
            self.progress_dialog.deleteLater()
            self.progress_dialog = None
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
