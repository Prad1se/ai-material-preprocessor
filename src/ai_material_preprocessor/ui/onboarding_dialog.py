from __future__ import annotations

import copy
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
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
from .mascot import mouse_asset_path
from .theme import stylesheet_for_theme
from .tool_installation import ToolInstallationCoordinator
from .tool_status_table import ToolStatusTable

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
        self.setWindowTitle("欢迎使用 AI 素材预处理工具")
        self.resize(860, 680)
        self.setMinimumSize(720, 580)
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
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(16)
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
        pixmap = QPixmap(str(mouse_asset_path("mouse-grin.png")))
        if not pixmap.isNull():
            self.mouse_mascot.setPixmap(
                pixmap.scaled(
                    self.mouse_mascot.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        hero.addLayout(copy_layout, 1)
        hero.addWidget(self.mouse_mascot)
        root.addLayout(hero)

        self.privacy_text = QLabel(
            "隐私承诺：文件默认只在本机处理，不会自动上传；原文件永不覆盖。"
            "只有 AI 资料包模式才创建资料包目录。"
        )
        self.privacy_text.setObjectName("outputHint")
        self.privacy_text.setWordWrap(True)
        root.addWidget(self.privacy_text)

        capability_title = QLabel("本机能力检查")
        capability_title.setObjectName("sectionTitle")
        root.addWidget(capability_title)
        self.tool_table = ToolStatusTable()
        root.addWidget(self.tool_table, 1)

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
        root.addLayout(actions)

    def _render_tools(self) -> None:
        self.tool_table.set_capabilities(build_tool_capabilities(self.tools))

    def _redetect(self) -> None:
        self.tools = self.detector(copy.deepcopy(self.config))
        self._render_tools()

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
