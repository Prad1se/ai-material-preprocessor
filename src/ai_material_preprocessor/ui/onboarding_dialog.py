from __future__ import annotations

import copy
from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..models import ToolStatus
from ..services.config import save_config
from ..services.tool_capabilities import build_tool_capabilities
from ..services.tool_versions import detect_tools_with_versions
from .background_tasks import BackgroundCall, start_background_call
from .mascot import mouse_asset_path
from .theme import stylesheet_for_theme
from .tool_installation import ToolInstallationCoordinator
from .tool_status_table import ToolStatusTable
from .window_sizing import fit_dialog_to_available_space

ConfigSaver = Callable[[dict], object]
ToolDetector = Callable[[dict], dict[str, ToolStatus]]


class OnboardingDialog(QDialog):
    onboarding_completed = Signal(object, object)

    def __init__(
        self,
        config: dict,
        tools: dict[str, ToolStatus],
        parent=None,
        *,
        save_callback: ConfigSaver = save_config,
        detector: ToolDetector = detect_tools_with_versions,
    ) -> None:
        super().__init__(parent)
        self.config = copy.deepcopy(config)
        self.tools = dict(tools)
        self.save_callback = save_callback
        self.detector = detector
        self._detection: BackgroundCall | None = None
        self.setWindowTitle("欢迎使用 AI 素材预处理工具")
        fit_dialog_to_available_space(self, 860, 680, minimum_width=640, minimum_height=500)
        self._build_ui()
        self.tool_installation = ToolInstallationCoordinator(
            self,
            self.config,
            save_callback=self.save_callback,
            detector=self.detector,
            changed_callback=self._tools_changed,
        )
        self.tool_table.install_requested.connect(self.tool_installation.request)
        self._render_tools()
        self.setStyleSheet(stylesheet_for_theme(self.config["app"].get("theme", "system")))

    def _build_ui(self) -> None:
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(32, 28, 32, 28)
        self.root_layout.setSpacing(16)
        hero = QHBoxLayout()
        copy_layout = QVBoxLayout()
        eyebrow = QLabel("第一次见面 · 鼠鼠先检查工作环境")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("欢迎来到本地 AI 素材工作台")
        title.setObjectName("title")
        title.setWordWrap(True)
        subtitle = QLabel("把文档准备给 AI，把视频整理成可继续创作的素材。")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        copy_layout.addWidget(eyebrow)
        copy_layout.addWidget(title)
        copy_layout.addWidget(subtitle)
        self.mouse_mascot = QLabel()
        self.mouse_mascot.setObjectName("mouseMascot")
        self.mouse_mascot.setFixedSize(190, 170)
        self.mouse_mascot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mouse_pixmap = QPixmap(str(mouse_asset_path("mouse-grin.png")))
        self._scale_mouse_mascot()
        hero.addLayout(copy_layout, 1)
        hero.addWidget(self.mouse_mascot)
        self.root_layout.addLayout(hero)

        self.privacy_text = QLabel(
            "隐私承诺：文件默认只在本机处理，不会自动上传；原文件永不覆盖。"
            "只有 AI 资料包模式才创建资料包目录。"
        )
        self.privacy_text.setObjectName("outputHint")
        self.privacy_text.setWordWrap(True)
        self.root_layout.addWidget(self.privacy_text)

        capability_title = QLabel("本机能力检查")
        capability_title.setObjectName("sectionTitle")
        self.root_layout.addWidget(capability_title)
        self.tool_table = ToolStatusTable()
        self.root_layout.addWidget(self.tool_table, 1)

        actions = QHBoxLayout()
        self.redetect_button = QPushButton("重新检测")
        self.redetect_button.clicked.connect(self._redetect)
        later = QPushButton("稍后再说")
        later.clicked.connect(self.reject)
        finish = QPushButton("开始使用")
        finish.setObjectName("primary")
        finish.clicked.connect(self._finish)
        actions.addWidget(self.redetect_button)
        actions.addStretch()
        actions.addWidget(later)
        actions.addWidget(finish)
        self.root_layout.addLayout(actions)
        self._apply_responsive_layout()

    def _render_tools(self) -> None:
        self.tool_table.set_capabilities(build_tool_capabilities(self.tools))

    def _redetect(self) -> None:
        if self._detection is not None:
            self._detection.cancel()
        self.redetect_button.setEnabled(False)
        detector = self.detector
        config = copy.deepcopy(self.config)
        worker = BackgroundCall(lambda: detector(config))
        self._detection = worker
        worker.succeeded.connect(self._detection_succeeded)
        worker.failed.connect(self._detection_failed)
        start_background_call(worker)

    def _detection_succeeded(self, raw_tools: object) -> None:
        if self.sender() is not self._detection or not isinstance(raw_tools, dict):
            return
        self._detection = None
        self.tools = raw_tools
        self._render_tools()
        self.redetect_button.setEnabled(True)

    def _detection_failed(self, message: str) -> None:
        if self.sender() is not self._detection:
            return
        self._detection = None
        self.redetect_button.setEnabled(True)
        QMessageBox.warning(self, "无法检测工具", message or "工具检测未完成，请稍后重试。")

    def _tools_changed(self, config: dict, tools: dict[str, ToolStatus]) -> None:
        self.config = copy.deepcopy(config)
        self.tools = dict(tools)
        self._render_tools()

    def _finish(self) -> None:
        candidate = copy.deepcopy(self.config)
        candidate["app"]["onboarding_completed"] = True
        try:
            self.save_callback(candidate)
        except OSError as exc:
            QMessageBox.critical(self, "无法保存首次设置", f"请检查应用数据目录权限。\n\n{exc}")
            return
        self.config = candidate
        self.tool_installation.update_config(candidate)
        self.onboarding_completed.emit(copy.deepcopy(candidate), dict(self.tools))
        self.accept()

    def event(self, event: QEvent) -> bool:
        if event.type() is QEvent.Type.Close:
            self._cancel_detection()
        return super().event(event)

    def reject(self) -> None:
        self._cancel_detection()
        super().reject()

    def _cancel_detection(self) -> None:
        self.tool_installation.cancel_detection()
        if self._detection is not None:
            self._detection.cancel()
            self._detection = None

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "root_layout"):
            self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        compact = self.height() < 600
        if compact:
            self.root_layout.setContentsMargins(20, 16, 20, 16)
            self.root_layout.setSpacing(10)
            self.mouse_mascot.setFixedSize(120, 100)
            self.tool_table.setMinimumHeight(120)
        else:
            self.root_layout.setContentsMargins(32, 28, 32, 28)
            self.root_layout.setSpacing(16)
            self.mouse_mascot.setFixedSize(190, 170)
            self.tool_table.setMinimumHeight(260)
        self._scale_mouse_mascot()

    def _scale_mouse_mascot(self) -> None:
        if self._mouse_pixmap.isNull():
            self.mouse_mascot.clear()
            return
        self.mouse_mascot.setPixmap(
            self._mouse_pixmap.scaled(
                self.mouse_mascot.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
