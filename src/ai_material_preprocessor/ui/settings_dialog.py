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

from ..apps.documents.policy import DOCUMENT_TOOL_NAMES
from ..apps.video.policy import VIDEO_TOOL_NAMES
from ..models import ToolStatus
from ..services.config import save_config
from ..services.tool_capabilities import TOOL_DESCRIPTORS, build_tool_capabilities
from ..services.tool_versions import detect_tools_with_versions
from .theme import ThemeMode, stylesheet_for_theme
from .tool_installation import ToolInstallationCoordinator
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
        self.document_tool_paths: dict[str, QLineEdit] = {}
        self.video_tool_paths: dict[str, QLineEdit] = {}
        self.setWindowTitle("设置")
        self.resize(900, 680)
        self.setMinimumSize(760, 580)
        self._build_ui()
        self.tool_installation = ToolInstallationCoordinator(
            self,
            self.config,
            save_callback=self.save_callback,
            detector=self.detector,
            changed_callback=self._tools_changed,
        )
        self.document_tool_table.install_requested.connect(self._request_tool_install)
        self.video_tool_table.install_requested.connect(self._request_tool_install)
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
        tabs.setObjectName("settingsTabs")

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
        install_row = QHBoxLayout()
        self.tool_install_directory = QLineEdit(
            str(self.config.get("tool_management", {}).get("install_directory", ""))
        )
        self.tool_install_directory.setPlaceholderText(
            "默认使用应用数据目录；可改为 D 盘等空间充足的位置"
        )
        install_browse = QPushButton("选择目录…")
        install_browse.clicked.connect(self._browse_install_directory)
        install_row.addWidget(self.tool_install_directory, 1)
        install_row.addWidget(install_browse)
        general_form.addRow("工具补充目录", install_row)
        tabs.addTab(general, "常规")

        documents_page, self.document_tool_table, document_scroll = self._tool_page(
            DOCUMENT_TOOL_NAMES, self.document_tool_paths
        )
        video_page, self.video_tool_table, video_scroll = self._tool_page(
            VIDEO_TOOL_NAMES, self.video_tool_paths
        )
        documents_page.layout().insertWidget(0, self._document_defaults())
        video_page.layout().insertWidget(0, self._video_defaults())
        self.tool_path_inputs.update(self.document_tool_paths)
        self.tool_path_inputs.update(self.video_tool_paths)
        # Compatibility aliases for callers that only need a table/scroll widget.
        self.tool_table = self.document_tool_table
        self.tool_path_scroll = document_scroll
        self.video_tool_path_scroll = video_scroll
        tabs.addTab(documents_page, "Documents")
        tabs.addTab(video_page, "Video")
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

    def _tool_page(
        self,
        tool_names: frozenset[str],
        path_inputs: dict[str, QLineEdit],
    ) -> tuple[QWidget, ToolStatusTable, QScrollArea]:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel("可用能力会自动检测；自定义路径优先于随程序提供和系统 PATH。")
        hint.setObjectName("sectionDescription")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        table = ToolStatusTable()
        layout.addWidget(table)
        paths_widget = QWidget()
        path_form = QFormLayout(paths_widget)
        for key, descriptor in TOOL_DESCRIPTORS.items():
            if key not in tool_names or not descriptor.custom_path_supported:
                continue
            row = QHBoxLayout()
            field = QLineEdit(str(self.config["tools"].get(key, "")))
            field.setPlaceholderText("自动检测")
            browse = QPushButton("选择…")
            browse.clicked.connect(lambda _checked=False, name=key: self._browse_tool(name))
            row.addWidget(field, 1)
            row.addWidget(browse)
            path_form.addRow(descriptor.display_name, row)
            path_inputs[key] = field
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(150)
        scroll.setWidget(paths_widget)
        layout.addWidget(scroll, 1)
        redetect = QPushButton("重新检测")
        redetect.clicked.connect(self._redetect)
        layout.addWidget(redetect)
        return page, table, scroll

    def _document_defaults(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("settingsGroup")
        form = QFormLayout(panel)
        self.document_mode = QComboBox()
        self.document_mode.addItem("AI 增强", "enhanced")
        self.document_mode.addItem("原始转换", "raw")
        self.document_mode.setCurrentIndex(
            max(0, self.document_mode.findData(str(self.config["document"]["mode"])))
        )
        self.document_split = QCheckBox("按 AI 易读长度自动拆分")
        self.document_split.setChecked(bool(self.config["document"]["split_enabled"]))
        self.document_target_tokens = QSpinBox()
        self.document_target_tokens.setRange(500, 100000)
        self.document_target_tokens.setSingleStep(500)
        self.document_target_tokens.setValue(int(self.config["document"]["target_tokens"]))
        self.document_target_tokens.setSuffix(" 估算 tokens / 段")
        self.document_ocr = QCheckBox("默认启用本地 OCR")
        self.document_ocr.setChecked(bool(self.config["document"]["ocr_enabled"]))
        form.addRow("处理模式", self.document_mode)
        form.addRow("自动拆分", self.document_split)
        form.addRow("目标长度", self.document_target_tokens)
        form.addRow("OCR", self.document_ocr)
        return panel

    def _video_defaults(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("settingsGroup")
        form = QFormLayout(panel)
        self.video_crf = QSpinBox()
        self.video_crf.setRange(0, 51)
        self.video_crf.setValue(int(self.config["video"]["compression_crf"]))
        self.video_audio_format = QComboBox()
        self.video_audio_format.addItem("MP3", "mp3")
        self.video_audio_format.addItem("WAV", "wav")
        self.video_audio_format.setCurrentIndex(
            max(
                0,
                self.video_audio_format.findData(str(self.config["video"]["audio_format"])),
            )
        )
        self.video_rename_template = QLineEdit(str(self.config["video"]["rename_template"]))
        self.video_project_name = QLineEdit(str(self.config["video"].get("project_name", "")))
        form.addRow("压缩 CRF", self.video_crf)
        form.addRow("音频格式", self.video_audio_format)
        form.addRow("命名模板", self.video_rename_template)
        form.addRow("默认项目", self.video_project_name)
        return panel

    def _config_from_fields(self) -> dict:
        result = copy.deepcopy(self.config)
        result["app"]["theme"] = str(self.theme_combo.currentData())
        result["app"]["update_check_enabled"] = self.update_check_enabled.isChecked()
        result["output_folder_name"] = self.output_folder_name.text().strip() or "AI素材处理结果"
        result["history"]["retention_days"] = self.retention_days.value()
        result["history"]["max_size_mb"] = self.history_size_mb.value()
        result["tool_management"]["install_directory"] = self.tool_install_directory.text().strip()
        result["document"].update(
            {
                "mode": str(self.document_mode.currentData()),
                "split_enabled": self.document_split.isChecked(),
                "target_tokens": self.document_target_tokens.value(),
                "ocr_enabled": self.document_ocr.isChecked(),
            }
        )
        result["video"].update(
            {
                "compression_crf": self.video_crf.value(),
                "audio_format": str(self.video_audio_format.currentData()),
                "rename_template": self.video_rename_template.text().strip()
                or "{date}_{time}_{location}_{index}",
                "project_name": self.video_project_name.text().strip(),
            }
        )
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

    def _browse_install_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择工具补充目录",
            self.tool_install_directory.text().strip(),
        )
        if selected:
            self.tool_install_directory.setText(selected)

    def _render_tools(self) -> None:
        capabilities = build_tool_capabilities(self.tools)
        self.document_tool_table.set_capabilities(
            tuple(item for item in capabilities if item.key in DOCUMENT_TOOL_NAMES)
        )
        self.video_tool_table.set_capabilities(
            tuple(item for item in capabilities if item.key in VIDEO_TOOL_NAMES)
        )

    def _redetect(self) -> None:
        candidate = self._config_from_fields()
        self.tools = self.detector(candidate)
        self._render_tools()

    def _tools_changed(self, config: dict, tools: dict[str, ToolStatus]) -> None:
        self.config = copy.deepcopy(config)
        self.tools = dict(tools)
        for key, field in self.tool_path_inputs.items():
            field.setText(str(self.config["tools"].get(key, "")))
        self.tool_install_directory.setText(
            str(self.config["tool_management"].get("install_directory", ""))
        )
        self._render_tools()
        self.settings_saved.emit(copy.deepcopy(self.config), dict(self.tools))

    def _request_tool_install(self, key: str) -> None:
        candidate = self._config_from_fields()
        self.tool_installation.update_config(candidate)
        self.tool_installation.request(key)

    def _save(self) -> None:
        candidate = self._config_from_fields()
        try:
            self.save_callback(candidate)
        except OSError as exc:
            QMessageBox.critical(self, "无法保存设置", f"请检查应用数据目录权限。\n\n{exc}")
            return
        self.config = candidate
        self.tool_installation.update_config(candidate)
        self.tools = self.detector(candidate)
        self.settings_saved.emit(copy.deepcopy(candidate), dict(self.tools))
        self.accept()
