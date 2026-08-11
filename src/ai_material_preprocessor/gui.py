from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .capabilities import available_operations
from .models import Job, Operation, TaskStatus, ToolStatus
from .services.config import load_config, save_config
from .services.environment import detect_tools
from .services.history_repository import HistoryRepository, default_cache_root
from .services.input_discovery import discover_input_files
from .services.metadata import read_media_metadata
from .services.preview import (
    build_batch_rename_preview,
    build_video_preview,
    completed_contact_sheet,
    resolve_batch_output_collisions,
)
from .services.task_manifest import (
    clear_history,
    history_usage,
    resolve_history_root,
)
from .services.task_repository import PersistentTaskQueue
from .services.tool_capabilities import missing_feature_guidance
from .services.tool_versions import detect_tools_with_versions
from .services.video_management import annotate_duplicate_previews, find_duplicate_videos
from .ui.history_dialog import HistoryDialog
from .ui.mascot import MOUSE_STATE_ASSETS, mouse_asset_path
from .ui.onboarding_dialog import OnboardingDialog
from .ui.preview_dialog import (
    ContactSheetPreviewDialog,
    DocumentReportDialog,
    SourcePlanDialog,
    VideoPreviewDialog,
)
from .ui.settings_dialog import SettingsDialog
from .ui.task_center_panel import TaskCenterPanel
from .ui.theme import stylesheet_for_theme
from .ui.workers import Worker


class DropList(QListWidget):
    files_added = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)
        self.setToolTip("把文件拖到这里")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile()
            and (Path(url.toLocalFile()).is_file() or Path(url.toLocalFile()).is_dir())
        ]
        if paths:
            self.files_added.emit(paths)
            event.acceptProposedAction()


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        config: dict | None = None,
        tools: dict[str, ToolStatus] | None = None,
        task_repository: PersistentTaskQueue | None = None,
    ) -> None:
        super().__init__()
        self.config = config or load_config()
        self.tools = tools or detect_tools(self.config)
        self.paths: list[Path] = []
        self.worker: Worker | None = None
        self.last_worker: Worker | None = None
        self.last_outputs: list[str] = []
        self.task_repository = task_repository

        self.setWindowTitle("AI 素材预处理工具")
        self.resize(1120, 780)
        self.setMinimumSize(900, 680)
        self._build_ui()
        self._apply_style()
        if self.task_repository is not None:
            self._restore_task_queue()

    def _restore_task_queue(self) -> None:
        recovery_worker = Worker(
            [],
            self.tools,
            self.config,
            task_repository=self.task_repository,
        )
        recoverable = [
            task
            for task in recovery_worker.tasks
            if task.status in {TaskStatus.WAITING, TaskStatus.INTERRUPTED}
        ]
        if not recoverable:
            return
        self.last_worker = recovery_worker
        for task in recoverable:
            self.task_panel.upsert(
                task.task_id,
                task.job.source.name,
                task.job.operation.value,
                task.status,
                task.progress,
                task.error or task.message,
            )
        self.status.setText(f"发现 {len(recoverable)} 个上次未完成的任务；可在任务中心选择后重试。")

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("page")
        root = QVBoxLayout(central)
        root.setContentsMargins(46, 34, 46, 40)
        root.setSpacing(20)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(30, 24, 26, 22)
        hero_layout.setSpacing(20)
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(8)
        eyebrow = QLabel("LOCAL  ·  PRIVATE  ·  鼠鼠不碰原文件")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("鼠鼠帮你把素材，\n准备成下一步需要的样子。")
        title.setObjectName("title")
        subtitle = QLabel(
            "交给 AI、普通转换、准备创作都在这里完成。处理全程留在本机，原文件始终保留。"
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        hero_copy.addWidget(eyebrow)
        hero_copy.addWidget(title)
        hero_copy.addWidget(subtitle)
        hero_copy.addStretch()
        self.mouse_mascot = QLabel()
        self.mouse_mascot.setObjectName("mouseMascot")
        self.mouse_mascot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mouse_mascot.setFixedSize(230, 210)
        hero_layout.addLayout(hero_copy, 1)
        hero_layout.addWidget(self.mouse_mascot)
        root.addWidget(hero)

        workflow = QHBoxLayout()
        workflow.setSpacing(10)
        for index, label in enumerate(("1  选择素材", "2  识别能力", "3  鼠鼠处理", "4  保存结果")):
            step = QLabel(label)
            step.setObjectName("workflowActive" if index == 0 else "workflowStep")
            step.setAlignment(Qt.AlignmentFlag.AlignCenter)
            workflow.addWidget(step)
        root.addLayout(workflow)

        content_row = QHBoxLayout()
        content_row.setSpacing(18)

        files_frame = QFrame()
        files_frame.setObjectName("panel")
        files_layout = QVBoxLayout(files_frame)
        files_layout.setContentsMargins(24, 22, 24, 24)
        files_layout.setSpacing(14)
        file_header = QHBoxLayout()
        file_title = QLabel("把文件交给鼠鼠")
        file_title.setObjectName("sectionTitle")
        add_button = QPushButton("选择文件…")
        add_button.setObjectName("secondary")
        add_button.clicked.connect(self._choose_files)
        folder_button = QPushButton("选择文件夹…")
        folder_button.setObjectName("secondary")
        folder_button.clicked.connect(self._choose_folder)
        clear_button = QPushButton("清空")
        clear_button.setObjectName("secondary")
        clear_button.clicked.connect(self._clear_files)
        file_header.addWidget(file_title)
        file_header.addStretch()
        file_header.addWidget(add_button)
        file_header.addWidget(folder_button)
        file_header.addWidget(clear_button)
        file_description = QLabel("拖入 Word、PPT、Excel、PDF、网页或视频；鼠鼠会自动判断可用操作")
        file_description.setObjectName("sectionDescription")
        self.file_list = DropList()
        self.file_list.setObjectName("dropZone")
        self.file_list.setMinimumHeight(280)
        self.file_list.files_added.connect(self._add_files)
        self.file_list.setAccessibleDescription("拖入 Word、PPT、Excel、PDF、HTML 或视频文件")
        files_layout.addLayout(file_header)
        files_layout.addWidget(file_description)
        files_layout.addWidget(self.file_list)
        content_row.addWidget(files_frame, 5)

        options_frame = QFrame()
        options_frame.setObjectName("panel")
        options_layout = QVBoxLayout(options_frame)
        options_layout.setContentsMargins(24, 22, 24, 24)
        options_layout.setSpacing(12)
        options_title = QLabel("鼠鼠要做什么")
        options_title.setObjectName("sectionTitle")
        options_description = QLabel("只显示当前素材真正可用的操作")
        options_description.setObjectName("sectionDescription")
        self.tool_hint = QLabel()
        self.tool_hint.setObjectName("toolHint")
        self.tool_hint.setWordWrap(True)
        self.tool_hint.setVisible(False)
        self.operation = QComboBox()
        self.operation.currentIndexChanged.connect(self._operation_changed)
        self.document_mode = QComboBox()
        self.document_mode.addItem("AI 增强 · 清洗、质检并可拆分", "enhanced")
        self.document_mode.addItem("原始转换 · 仅保留 MarkItDown 结果", "raw")
        configured_mode = str(self.config["document"]["mode"])
        self.document_mode.setCurrentIndex(1 if configured_mode == "raw" else 0)
        self.document_mode.currentIndexChanged.connect(self._operation_changed)
        self.split_document = QCheckBox("按 AI 易读长度自动拆分")
        self.split_document.setChecked(bool(self.config["document"]["split_enabled"]))
        self.target_tokens = QSpinBox()
        self.target_tokens.setRange(500, 100000)
        self.target_tokens.setSingleStep(500)
        self.target_tokens.setSuffix(" 估算 tokens / 段")
        self.target_tokens.setValue(int(self.config["document"]["target_tokens"]))
        self.target_tokens.setToolTip("默认 4000；这是跨模型的保守估算，不是特定模型的精确计数。")
        self.ocr_enabled = QCheckBox("使用本地 OCR 识别扫描页和内嵌图片（较慢）")
        self.ocr_enabled.setChecked(bool(self.config["document"]["ocr_enabled"]))
        ocr_available = self.tools.get("rapidocr", ToolStatus("rapidocr", None)).available
        self.ocr_enabled.setEnabled(ocr_available)
        if not ocr_available:
            self.ocr_enabled.setToolTip("当前发布包未检测到 RapidOCR。普通转换和 AI 增强仍可使用。")
        self.quality = QComboBox()
        self.quality.addItem("高质量 · 文件较大（CRF 20）", 20)
        self.quality.addItem("均衡（CRF 23）", 23)
        self.quality.addItem("体积优先（CRF 28）", 28)
        configured_crf = int(self.config["video"]["compression_crf"])
        for index in range(self.quality.count()):
            if self.quality.itemData(index) == configured_crf:
                self.quality.setCurrentIndex(index)
                break
        self.audio_format = QComboBox()
        self.audio_format.addItem("MP3 · 兼容且体积小", "mp3")
        self.audio_format.addItem("WAV · 无损且适合剪辑", "wav")
        configured_audio = str(self.config["video"]["audio_format"]).lower()
        self.audio_format.setCurrentIndex(1 if configured_audio == "wav" else 0)
        self.scene_sensitivity = QComboBox()
        self.scene_sensitivity.addItem("关键帧：更多场景（灵敏度高）", 0.20)
        self.scene_sensitivity.addItem("关键帧：均衡", 0.30)
        self.scene_sensitivity.addItem("关键帧：只保留明显变化", 0.45)
        configured_threshold = float(self.config["video"]["scene_threshold"])
        self.scene_sensitivity.setCurrentIndex(
            min(
                range(self.scene_sensitivity.count()),
                key=lambda i: abs(float(self.scene_sensitivity.itemData(i)) - configured_threshold),
            )
        )
        self.max_keyframes = QSpinBox()
        self.max_keyframes.setRange(4, 60)
        self.max_keyframes.setSuffix(" 张关键帧上限")
        self.max_keyframes.setValue(int(self.config["video"]["max_keyframes"]))
        self.location = QLineEdit()
        self.location.setPlaceholderText("地点（可选；优先于视频元数据，例如：杭州西湖）")
        self.project_name = QLineEdit(str(self.config["video"].get("project_name", "")))
        self.project_name.setPlaceholderText("项目名称（可选，例如：毕业短片）")
        self.organize_mode = QComboBox()
        self.organize_mode.addItem("按日期和地点分层", "date_location")
        self.organize_mode.addItem("只按日期分层", "date")
        self.organize_mode.addItem("只按地点分层", "location")
        configured_organize = str(self.config["video"].get("organize_mode", "date_location"))
        for index in range(self.organize_mode.count()):
            if self.organize_mode.itemData(index) == configured_organize:
                self.organize_mode.setCurrentIndex(index)
                break
        self.rename_template = QLineEdit(str(self.config["video"]["rename_template"]))
        self.rename_template.setPlaceholderText("命名模板：{date}_{time}_{location}_{index}")
        self.rename_template.setToolTip(
            "支持日期时间、地点、坐标、分辨率、时长、编码、相机和原文件名等字段。"
        )
        self.preview_button = QPushButton("预览处理方案")
        self.preview_button.setObjectName("secondary")
        self.preview_button.clicked.connect(self._show_processing_preview)
        output_row = QHBoxLayout()
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("默认：原文件旁的“AI素材处理结果”")
        output_button = QPushButton("选择…")
        output_button.setObjectName("secondary")
        output_button.clicked.connect(self._choose_output)
        output_row.addWidget(self.output_path)
        output_row.addWidget(output_button)
        options_layout.addWidget(options_title)
        options_layout.addWidget(options_description)
        options_layout.addWidget(self.tool_hint)
        options_layout.addWidget(self.operation)
        options_layout.addWidget(self.document_mode)
        options_layout.addWidget(self.split_document)
        options_layout.addWidget(self.target_tokens)
        options_layout.addWidget(self.ocr_enabled)
        options_layout.addWidget(self.quality)
        options_layout.addWidget(self.audio_format)
        options_layout.addWidget(self.scene_sensitivity)
        options_layout.addWidget(self.max_keyframes)
        options_layout.addWidget(self.location)
        options_layout.addWidget(self.project_name)
        options_layout.addWidget(self.organize_mode)
        options_layout.addWidget(self.rename_template)
        options_layout.addWidget(self.preview_button)
        output_label = QLabel("保存到")
        output_label.setObjectName("fieldLabel")
        options_layout.addSpacing(6)
        options_layout.addWidget(output_label)
        options_layout.addLayout(output_row)
        self.output_hint = QLabel()
        self.output_hint.setObjectName("outputHint")
        self.output_hint.setWordWrap(True)
        options_layout.addWidget(self.output_hint)
        options_layout.addStretch()
        content_row.addWidget(options_frame, 4)
        root.addLayout(content_row)

        action_row = QHBoxLayout()
        self.start_button = QPushButton("开始处理")
        self.start_button.setObjectName("primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._start)
        self.open_button = QPushButton("打开结果")
        self.open_button.setObjectName("secondary")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_output)
        action_row.addWidget(self.start_button, 2)
        action_row.addWidget(self.open_button, 1)
        root.addLayout(action_row)

        self.task_panel = TaskCenterPanel()
        self.task_table = self.task_panel.table
        self.cancel_task_button = self.task_panel.cancel_button
        self.retry_task_button = self.task_panel.retry_button
        self.cancel_task_button.clicked.connect(self._cancel_selected_tasks)
        self.retry_task_button.clicked.connect(self._retry_selected_tasks)
        self.task_panel.selection_changed.connect(self._update_task_actions)
        root.addWidget(self.task_panel)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.status = QLabel("等待文件")
        self.status.setObjectName("status")
        root.addWidget(self.progress)
        root.addWidget(self.status)

        history_frame = QFrame()
        history_frame.setObjectName("historyBar")
        history_layout = QHBoxLayout(history_frame)
        history_layout.setContentsMargins(16, 10, 12, 10)
        self.history_label = QLabel("处理历史统一保存在应用数据目录，不会出现在导出文件中。")
        self.history_label.setObjectName("historyLabel")
        self.history_label.setToolTip(str(resolve_history_root(self.config)))
        self.history_button = QPushButton("查看历史记录")
        self.history_button.setObjectName("linkButton")
        self.history_button.clicked.connect(self._open_history)
        self.settings_button = QPushButton("设置")
        self.settings_button.setObjectName("linkButton")
        self.settings_button.clicked.connect(self._open_settings)
        self.clear_history_button = QPushButton("清除历史")
        self.clear_history_button.setObjectName("dangerLinkButton")
        self.clear_history_button.clicked.connect(self._clear_history)
        history_layout.addWidget(self.history_label)
        history_layout.addStretch()
        history_layout.addWidget(self.history_button)
        history_layout.addWidget(self.settings_button)
        history_layout.addWidget(self.clear_history_button)
        root.addWidget(history_frame)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)
        self._set_mouse_state("idle")
        self._operation_changed()

    def _set_mouse_state(self, state: str) -> None:
        state = state if state in MOUSE_STATE_ASSETS else "idle"
        pixmap = QPixmap(str(mouse_asset_path(MOUSE_STATE_ASSETS[state])))
        if not pixmap.isNull():
            self.mouse_mascot.setPixmap(
                pixmap.scaled(
                    self.mouse_mascot.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.mouse_mascot.setProperty("state", state)

    def _apply_style(self) -> None:
        self.setStyleSheet(stylesheet_for_theme(self.config["app"].get("theme", "system")))

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择素材文件")
        self._add_files(paths)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择素材文件夹")
        if path:
            self._add_files([path])

    def _add_files(self, paths: list[str]) -> None:
        known = {str(path).casefold() for path in self.paths}
        for path in discover_input_files(paths):
            key = str(path).casefold()
            if key in known:
                continue
            self.paths.append(path)
            self.file_list.addItem(str(path))
            known.add(key)
        self.paths.sort(key=lambda item: str(item).casefold())
        if self.paths:
            self._refresh_operations()
            self._set_mouse_state("thinking")

    def _clear_files(self) -> None:
        self.paths.clear()
        self.file_list.clear()
        self._refresh_operations()
        self.status.setText("等待文件")
        self._set_mouse_state("idle")

    def _settings_applied(self, config: dict, tools: dict[str, ToolStatus]) -> None:
        self.config = config
        self.tools = tools
        self._apply_style()
        ocr_available = self.tools.get("rapidocr", ToolStatus("rapidocr", None)).available
        self.ocr_enabled.setEnabled(ocr_available)
        self.ocr_enabled.setToolTip(
            "" if ocr_available else "当前未检测到本地 OCR；普通转换和 AI 增强仍可使用。"
        )
        self.history_label.setToolTip(str(resolve_history_root(self.config)))
        self._refresh_operations()

    def _open_settings(self) -> None:
        detected = detect_tools_with_versions(self.config)
        dialog = SettingsDialog(self.config, detected, self)
        dialog.settings_saved.connect(self._settings_applied)
        dialog.exec()

    def show_onboarding_if_needed(self) -> None:
        if bool(self.config["app"].get("onboarding_completed", False)):
            return
        self.tools = detect_tools_with_versions(self.config)
        self.onboarding_dialog = OnboardingDialog(self.config, self.tools, self)
        self.onboarding_dialog.onboarding_completed.connect(self._settings_applied)
        self.onboarding_dialog.setModal(False)
        self.onboarding_dialog.show()

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.output_path.setText(path)

    def _operation_changed(self) -> None:
        raw_operation = self.operation.currentData()
        if raw_operation is None:
            self.document_mode.setVisible(False)
            self.split_document.setVisible(False)
            self.target_tokens.setVisible(False)
            self.ocr_enabled.setVisible(False)
            self.quality.setVisible(False)
            self.audio_format.setVisible(False)
            self.scene_sensitivity.setVisible(False)
            self.max_keyframes.setVisible(False)
            self.location.setVisible(False)
            self.project_name.setVisible(False)
            self.organize_mode.setVisible(False)
            self.rename_template.setVisible(False)
            self.preview_button.setVisible(False)
            self.output_hint.setText("添加素材后，这里会说明最终生成单个文件还是资料包。")
            return
        operation = Operation(raw_operation)
        markdown = operation == Operation.TO_MARKDOWN
        enhanced = markdown and self.document_mode.currentData() == "enhanced"
        self.document_mode.setVisible(markdown)
        self.split_document.setVisible(enhanced)
        self.target_tokens.setVisible(enhanced)
        self.ocr_enabled.setVisible(enhanced)
        renaming = operation in {Operation.RENAME_VIDEO, Operation.ORGANIZE_VIDEO}
        organizing = operation == Operation.ORGANIZE_VIDEO
        self.quality.setVisible(operation == Operation.COMPRESS_VIDEO)
        self.audio_format.setVisible(operation == Operation.EXTRACT_AUDIO)
        storyboard = operation == Operation.KEYFRAMES_CONTACT_SHEET
        self.scene_sensitivity.setVisible(storyboard)
        self.max_keyframes.setVisible(storyboard)
        self.location.setVisible(renaming)
        self.project_name.setVisible(renaming)
        self.organize_mode.setVisible(organizing)
        self.rename_template.setVisible(renaming)
        self.preview_button.setVisible(True)
        if markdown and enhanced:
            self.output_hint.setText(
                "输出：一个精简 AI 资料包，包含清洗正文、按需拆分内容和 manifest.json；完成后弹窗显示质量检查。"
            )
        elif markdown:
            self.output_hint.setText("输出：单个 Markdown 文件，直接保存在所选目录。")
        elif operation == Operation.TO_PDF:
            self.output_hint.setText("输出：单个 PDF 文件，直接保存在所选目录。")
        elif operation == Operation.KEYFRAMES_CONTACT_SHEET:
            self.output_hint.setText(
                "输出：一个关键帧包文件夹，包含联系表、关键帧与 manifest.json。"
            )
        elif operation == Operation.ORGANIZE_VIDEO:
            self.output_hint.setText(
                "输出：按日期/地点目录保存命名副本；原视频不移动、不改名，操作写入统一历史。"
            )
        else:
            self.output_hint.setText("输出：单个处理结果文件，直接保存在所选目录。")
        hint = ""
        if (
            operation
            in {
                Operation.COMPRESS_VIDEO,
                Operation.EXTRACT_AUDIO,
                Operation.STANDARDIZE_MP4,
                Operation.KEYFRAMES_CONTACT_SHEET,
            }
            and not self.tools.get("ffmpeg", ToolStatus("ffmpeg", None)).available
        ):
            hint = "（需要安装 FFmpeg）"
        elif operation in {Operation.RENAME_VIDEO, Operation.ORGANIZE_VIDEO} and not any(
            self.tools.get(name, ToolStatus(name, None)).available
            for name in ("exiftool", "ffprobe", "ffmpeg")
        ):
            hint = "（未发现元数据工具，将使用文件时间；可手动填写地点）"
        self.status.setText(operation.value + hint)

    def _refresh_operations(self) -> None:
        previous = self.operation.currentData()
        self.operation.blockSignals(True)
        self.operation.clear()
        common: list[Operation] = []
        if self.paths:
            operation_sets = [set(available_operations(path, self.tools)) for path in self.paths]
            allowed = set.intersection(*operation_sets) if operation_sets else set()
            common = [operation for operation in Operation if operation in allowed]
            for operation in common:
                self.operation.addItem(operation.value, operation.value)
        if previous is not None:
            for index in range(self.operation.count()):
                if self.operation.itemData(index) == previous:
                    self.operation.setCurrentIndex(index)
                    break
        self.operation.blockSignals(False)
        self.start_button.setEnabled(bool(self.paths and common and self.worker is None))
        guidance = missing_feature_guidance(self.paths[0].suffix, self.tools) if self.paths else ""
        self.tool_hint.setText(guidance)
        self.tool_hint.setVisible(bool(guidance))
        if self.paths and not common:
            if guidance:
                self.status.setText("当前文件缺少所需本机能力；请打开设置重新检测或选择工具路径。")
            else:
                self.status.setText("所选文件没有共同可执行的操作，请按文档或视频分批处理。")
        elif self.paths:
            self.status.setText(f"已添加 {len(self.paths)} 个文件；请选择处理方式。")
        self._operation_changed()

    def _tool_path(self, name: str) -> str | None:
        status = self.tools.get(name)
        return status.path if status else None

    def _preview_parameters(self, operation: Operation) -> dict[str, object]:
        if operation is Operation.TO_MARKDOWN:
            enhanced = self.document_mode.currentData() == "enhanced"
            return {
                "模式": "AI 增强" if enhanced else "原始转换",
                "自动拆分": "是" if enhanced and self.split_document.isChecked() else "否",
                "目标长度": f"{self.target_tokens.value()} tokens",
                "OCR": "开启"
                if enhanced and self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
                else "关闭",
            }
        if operation is Operation.TO_PDF:
            return {"输出": "单个 PDF", "原文件": "保留"}
        if operation is Operation.COMPRESS_VIDEO:
            return {
                "compression_crf": int(self.quality.currentData()),
                "compression_preset": str(self.config["video"]["compression_preset"]),
            }
        if operation is Operation.EXTRACT_AUDIO:
            return {
                "audio_format": str(self.audio_format.currentData()),
                "audio_bitrate": str(self.config["video"]["audio_bitrate"]),
            }
        if operation is Operation.KEYFRAMES_CONTACT_SHEET:
            return {
                "scene_threshold": float(self.scene_sensitivity.currentData()),
                "max_keyframes": int(self.max_keyframes.value()),
                "columns": int(self.config["video"]["contact_sheet_columns"]),
            }
        if operation in {Operation.RENAME_VIDEO, Operation.ORGANIZE_VIDEO}:
            return {
                "rename_template": self.rename_template.text().strip()
                or "{date}_{time}_{location}_{index}",
                "project_name": self.project_name.text().strip(),
                "organize_mode": str(self.organize_mode.currentData()),
                "location_dictionary": dict(self.config["video"].get("location_dictionary", {})),
            }
        return {"输出编码": "H.264 / AAC", "容器": "MP4"}

    def _show_processing_preview(self) -> None:
        if not self.paths:
            return
        raw_operation = self.operation.currentData()
        if raw_operation is None:
            return
        operation = Operation(raw_operation)
        parameters = self._preview_parameters(operation)
        if operation in {Operation.TO_MARKDOWN, Operation.TO_PDF}:
            note = (
                "转换后将显示清洗后的 Markdown、标题结构、拆分长度、OCR 页面和风险提示。"
                if operation is Operation.TO_MARKDOWN
                else "普通 PDF 转换只生成目标文件；处理记录保存在应用数据目录。"
            )
            SourcePlanDialog(
                "文档处理参数预览",
                self.paths,
                {key: str(value) for key, value in parameters.items()},
                note,
                self,
            ).exec()
            return
        try:
            metadata = [
                read_media_metadata(
                    source,
                    self._tool_path("exiftool"),
                    self._tool_path("ffprobe"),
                    ffmpeg=self._tool_path("ffmpeg"),
                )
                for source in self.paths
            ]
            if operation is Operation.RENAME_VIDEO:
                raw_dictionary = parameters["location_dictionary"]
                location_dictionary = (
                    {str(key): str(value) for key, value in raw_dictionary.items()}
                    if isinstance(raw_dictionary, dict)
                    else {}
                )
                previews = list(
                    build_batch_rename_preview(
                        self.paths,
                        metadata,
                        self._job_output(self.paths[0]),
                        template=str(parameters["rename_template"]),
                        manual_location=self.location.text(),
                        project_name=str(parameters["project_name"]),
                        location_dictionary=location_dictionary,
                    )
                )
            else:
                previews = [
                    build_video_preview(
                        source,
                        item,
                        operation,
                        self._job_output(source),
                        parameters=parameters,
                        index=index,
                        manual_location=self.location.text(),
                    )
                    for index, (source, item) in enumerate(
                        zip(self.paths, metadata, strict=True), start=1
                    )
                ]
            previews = list(resolve_batch_output_collisions(previews))
            previews = list(
                annotate_duplicate_previews(
                    previews,
                    find_duplicate_videos(self.paths, metadata),
                )
            )
        except Exception as exc:
            QMessageBox.critical(self, "无法生成预览", str(exc))
            return
        VideoPreviewDialog(previews, self).exec()

    def _job_output(self, source: Path) -> Path:
        explicit = self.output_path.text().strip()
        if explicit:
            return Path(explicit).resolve()
        return source.parent / str(self.config["output_folder_name"])

    def _start(self) -> None:
        if not self.paths:
            QMessageBox.information(self, "还没有文件", "请先添加至少一个文件。")
            return
        if self.operation.currentData() is None:
            return
        operation = Operation(self.operation.currentData())
        self.config["video"]["compression_crf"] = int(self.quality.currentData())
        self.config["video"]["audio_format"] = str(self.audio_format.currentData())
        self.config["video"]["rename_template"] = (
            self.rename_template.text().strip() or "{date}_{time}_{location}_{index}"
        )
        self.config["video"]["project_name"] = self.project_name.text().strip()
        self.config["video"]["organize_mode"] = str(self.organize_mode.currentData())
        self.config["video"]["scene_threshold"] = float(self.scene_sensitivity.currentData())
        self.config["video"]["max_keyframes"] = int(self.max_keyframes.value())
        self.config["document"]["mode"] = str(self.document_mode.currentData())
        self.config["document"]["split_enabled"] = self.split_document.isChecked()
        self.config["document"]["target_tokens"] = int(self.target_tokens.value())
        self.config["document"]["max_tokens"] = max(
            int(self.target_tokens.value()) + 1000,
            int(self.config["document"].get("max_tokens", 6000)),
        )
        self.config["document"]["ocr_enabled"] = (
            self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
        )
        with suppress(OSError):
            save_config(self.config)
        jobs = [
            Job(
                source=path,
                operation=operation,
                output_root=self._job_output(path),
                location=self.location.text(),
                project=self.project_name.text().strip(),
            )
            for path in self.paths
        ]
        self.start_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.progress.setValue(0)
        self._set_mouse_state("working")
        self.worker = Worker(
            jobs,
            self.tools,
            self.config,
            task_repository=self.task_repository,
        )
        for task in self.worker.tasks:
            if task.task_id in self.worker.tracked_ids:
                self.task_panel.upsert(
                    task.task_id,
                    task.job.source.name,
                    task.job.operation.value,
                    task.status,
                    task.progress,
                    task.message,
                )
        self.worker.progress.connect(self._on_progress)
        self.worker.task_changed.connect(self._on_task_changed)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failure)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _on_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.status.setText(message)
        self._set_mouse_state("working")

    def _on_task_changed(
        self,
        task_id: str,
        status_value: str,
        progress: int,
        message: str,
    ) -> None:
        worker = self.worker or self.last_worker
        task = (
            next((item for item in worker.tasks if item.task_id == task_id), None)
            if worker
            else None
        )
        if task is None:
            return
        self.task_panel.upsert(
            task_id,
            task.job.source.name,
            task.job.operation.value,
            TaskStatus(status_value),
            progress,
            message,
        )
        self._update_task_actions()

    def _update_task_actions(self) -> None:
        worker = self.worker or self.last_worker
        states = {task.task_id: task.status for task in worker.tasks} if worker else {}
        self.task_panel.update_actions(
            running=self.worker is not None,
            states=states,
        )

    def _cancel_selected_tasks(self) -> None:
        if self.worker is None:
            return
        for task_id in self.task_panel.selected_task_ids():
            self.worker.cancel_task(task_id)
        self._update_task_actions()

    def _retry_selected_tasks(self) -> None:
        if self.worker is not None or self.last_worker is None:
            return
        retried = self.last_worker.retry_tasks(self.task_panel.selected_task_ids())
        if not retried:
            return
        self.worker = self.last_worker
        self.last_worker = None
        self.start_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self._set_mouse_state("working")
        self.worker.start()

    @staticmethod
    def _quality_report_text(reports: list[dict], outputs: list[str]) -> str:
        sections: list[str] = []
        for report in reports:
            sections.append(
                f"{report['source']}\n"
                f"质量分：{report['score']}/100    "
                f"估算长度：{report['estimated_tokens']} tokens\n"
                f"标题：{report['heading_count']}    图片：{report['image_count']}"
            )
            issues = report.get("issues") or []
            if issues:
                sections.append(
                    "需要注意：\n" + "\n".join(f"• {issue['message']}" for issue in issues[:6])
                )
            else:
                sections.append("未发现明显问题。")
        if outputs:
            sections.append("输出位置：\n" + "\n".join(outputs[:3]))
        return "\n\n".join(sections)

    def _on_completed(
        self, outputs: list[str], errors: list[str], quality_reports: list[dict]
    ) -> None:
        self.last_outputs = outputs
        self._set_mouse_state("success" if outputs else "error")
        self.open_button.setEnabled(bool(outputs))
        if quality_reports:
            DocumentReportDialog(quality_reports, outputs, self).exec()
            if errors:
                QMessageBox.warning(self, "部分任务未完成", "\n".join(errors[:6]))
            self.status.setText(
                f"处理完成：已生成 {len(outputs)} 项；质量检查已显示，原文件未改动。"
            )
            return
        if errors:
            self.status.setText(
                f"处理结束：成功 {len(outputs)} 个，失败 {len(errors)} 个；原文件未改动。"
            )
            QMessageBox.warning(
                self,
                "部分任务未完成",
                "成功生成：" + str(len(outputs)) + "\n\n" + "\n".join(errors[:8]),
            )
        else:
            self.status.setText(f"处理完成：已生成 {len(outputs)} 个文件，原文件未改动。")
            contact_sheet = next(
                (
                    path
                    for raw in outputs
                    if (path := completed_contact_sheet(Path(raw))) is not None
                ),
                None,
            )
            if contact_sheet is not None:
                source_name = self.paths[0].name if self.paths else contact_sheet.parent.name
                ContactSheetPreviewDialog(source_name, contact_sheet, self).exec()
            else:
                QMessageBox.information(
                    self,
                    "处理完成",
                    "已生成：\n" + "\n".join(outputs[:5]) + ("\n…" if len(outputs) > 5 else ""),
                )

    def _worker_finished(self) -> None:
        self.last_worker = self.worker
        self.worker = None
        self._refresh_operations()
        self._update_task_actions()

    def _on_failure(self, message: str) -> None:
        self.status.setText("处理失败；原文件未改动。")
        self._set_mouse_state("error")
        QMessageBox.critical(self, "处理失败", message)

    def _open_output(self) -> None:
        if not self.last_outputs:
            return
        folder = str(Path(self.last_outputs[0]).parent)
        if os.name == "nt":
            os.startfile(folder)

    def _open_history(self) -> None:
        history = resolve_history_root(self.config)
        dialog = HistoryDialog(
            HistoryRepository(history, cache_root=default_cache_root()),
            self,
        )
        dialog.exec()

    @staticmethod
    def _format_bytes(value: int) -> str:
        size = float(value)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    def _clear_history(self) -> None:
        history = resolve_history_root(self.config)
        usage = history_usage(history)
        if usage.task_count == 0 and usage.total_bytes == 0:
            QMessageBox.information(self, "没有历史记录", "当前没有可清除的处理历史。")
            return
        answer = QMessageBox.question(
            self,
            "清除全部历史记录？",
            f"将永久删除 {usage.task_count} 条记录，约 {self._format_bytes(usage.total_bytes)}。\n\n"
            "这不会删除任何原文件或转换结果，但历史记录无法恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = clear_history(history)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "清除失败", str(exc))
            return
        self.status.setText(f"已清除 {removed.task_count} 条历史记录。")
        QMessageBox.information(
            self,
            "历史记录已清除",
            f"已永久删除 {removed.task_count} 条记录，释放 {self._format_bytes(removed.total_bytes)}。",
        )


def launch_for_smoke_test() -> MainWindow:
    """Build a window without starting the event loop."""
    if QApplication.instance() is None:
        QApplication([])
    return MainWindow()
