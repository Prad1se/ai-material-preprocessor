from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..models import ToolStatus
from ..services.config import save_config
from ..services.tool_capabilities import TOOL_DESCRIPTORS, build_tool_capabilities
from ..services.tool_versions import detect_tools_with_versions
from .theme import ThemeMode, stylesheet_for_theme
from .tool_status_table import ToolStatusTable

ConfigSaver = Callable[[dict], object]
ToolDetector = Callable[[dict], dict[str, ToolStatus]]


class SettingsDialog(QDialog):
    settings_saved = Signal(object, object)

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
        self.tool_path_inputs: dict[str, QLineEdit] = {}
        self.setWindowTitle("设置")
        self.resize(900, 680)
        self.setMinimumSize(760, 580)
        self._build_ui()
        self._render_tools()
        self.setStyleSheet(stylesheet_for_theme(self.config["app"].get("theme", "system")))

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        title = QLabel("设置")
        title.setObjectName("sectionTitle")
        subtitle = QLabel("所有工具路径和偏好都只保存在本机应用数据目录。")
        subtitle.setObjectName("sectionDescription")
        root.addWidget(title)
        root.addWidget(subtitle)
        tabs = QTabWidget()

        general = QWidget()
        general_form = QFormLayout(general)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随 Windows", ThemeMode.SYSTEM.value)
        self.theme_combo.addItem("浅色", ThemeMode.LIGHT.value)
        self.theme_combo.addItem("深色", ThemeMode.DARK.value)
        configured_theme = str(self.config["app"].get("theme", ThemeMode.SYSTEM.value))
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(configured_theme)))
        self.output_folder_name = QLineEdit(str(self.config["output_folder_name"]))
        self.retention_days = QSpinBox()
        self.retention_days.setRange(1, 3650)
        self.retention_days.setValue(int(self.config["history"]["retention_days"]))
        self.retention_days.setSuffix(" 天")
        self.history_size_mb = QSpinBox()
        self.history_size_mb.setRange(32, 102400)
        self.history_size_mb.setValue(int(self.config["history"]["max_size_mb"]))
        self.history_size_mb.setSuffix(" MB")
        self.update_check_enabled = QCheckBox("允许连接 GitHub 检查新版本")
        self.update_check_enabled.setChecked(
            bool(self.config["app"].get("update_check_enabled", False))
        )
        self.update_check_enabled.setToolTip(
            "默认关闭。开启后仅在你点击“检查更新”时访问 GitHub Releases，不上传文件。"
        )
        general_form.addRow("界面主题", self.theme_combo)
        general_form.addRow("默认结果目录名", self.output_folder_name)
        general_form.addRow("历史保留期限", self.retention_days)
        general_form.addRow("历史容量上限", self.history_size_mb)
        general_form.addRow("联网更新检查", self.update_check_enabled)
        tabs.addTab(general, "常规")

        tools_page = QWidget()
        tools_layout = QVBoxLayout(tools_page)
        hint = QLabel("可用能力会自动检测；自定义路径优先于随程序提供和系统 PATH。")
        hint.setObjectName("sectionDescription")
        hint.setWordWrap(True)
        tools_layout.addWidget(hint)
        self.tool_table = ToolStatusTable()
        tools_layout.addWidget(self.tool_table)
        paths_widget = QWidget()
        path_form = QFormLayout(paths_widget)
        for key, descriptor in TOOL_DESCRIPTORS.items():
            if not descriptor.custom_path_supported:
                continue
            row = QHBoxLayout()
            field = QLineEdit(str(self.config["tools"].get(key, "")))
            field.setPlaceholderText("自动检测")
            browse = QPushButton("选择…")
            browse.clicked.connect(lambda _checked=False, name=key: self._browse_tool(name))
            row.addWidget(field, 1)
            row.addWidget(browse)
            path_form.addRow(descriptor.display_name, row)
            self.tool_path_inputs[key] = field
        self.tool_path_scroll = QScrollArea()
        self.tool_path_scroll.setWidgetResizable(True)
        self.tool_path_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tool_path_scroll.setMinimumHeight(180)
        self.tool_path_scroll.setWidget(paths_widget)
        tools_layout.addWidget(self.tool_path_scroll, 1)
        self.redetect_button = QPushButton("重新检测")
        self.redetect_button.clicked.connect(self._redetect)
        tools_layout.addWidget(self.redetect_button)
        tabs.addTab(tools_page, "本机能力")
        root.addWidget(tabs, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存设置")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addLayout(actions)

    def _config_from_fields(self) -> dict:
        result = copy.deepcopy(self.config)
        result["app"]["theme"] = str(self.theme_combo.currentData())
        result["app"]["update_check_enabled"] = self.update_check_enabled.isChecked()
        result["output_folder_name"] = self.output_folder_name.text().strip() or "AI素材处理结果"
        result["history"]["retention_days"] = self.retention_days.value()
        result["history"]["max_size_mb"] = self.history_size_mb.value()
        for key, field in self.tool_path_inputs.items():
            result["tools"][key] = field.text().strip()
        return result

    def _browse_tool(self, key: str) -> None:
        current = self.tool_path_inputs[key].text().strip()
        selected, _ = QFileDialog.getOpenFileName(
            self,
            f"选择 {TOOL_DESCRIPTORS[key].display_name}",
            str(Path(current).parent) if current else "",
            "可执行文件 (*.exe);;所有文件 (*)",
        )
        if selected:
            self.tool_path_inputs[key].setText(selected)

    def _render_tools(self) -> None:
        self.tool_table.set_capabilities(build_tool_capabilities(self.tools))

    def _redetect(self) -> None:
        candidate = self._config_from_fields()
        self.tools = self.detector(candidate)
        self._render_tools()

    def _save(self) -> None:
        candidate = self._config_from_fields()
        try:
            self.save_callback(candidate)
        except OSError as exc:
            QMessageBox.critical(self, "无法保存设置", f"请检查应用数据目录权限。\n\n{exc}")
            return
        self.config = candidate
        self.tools = self.detector(candidate)
        self.settings_saved.emit(copy.deepcopy(candidate), dict(self.tools))
        self.accept()
