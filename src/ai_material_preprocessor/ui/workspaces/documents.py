from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...application.preview_registry import PreviewRequest
from ...application.workspaces import WorkspaceId
from ...apps.documents.presets import DOCUMENT_PRESETS, PRESET_BY_ID
from ...apps.documents.workspace_controller import (
    DocumentOperationAvailability,
    DocumentWorkspaceController,
)
from ...models import Operation, ToolStatus
from ...services.context_copy import build_context_copy
from ...services.context_summary import ContextPackSummary, summarize_context_pack
from ...services.source_open import (
    SourceOpenCapability,
    SourceOpenTarget,
    source_paths_by_id,
)
from ..document_mascot import DocumentMascotState, DocumentMascotView
from ..source_map_view import SourceMapView
from .common import WorkspacePresentationState, WorkspaceView

_OPERATION_LABELS = {
    Operation.TO_MARKDOWN: "AI 就绪 Markdown",
    Operation.TO_PDF: "创建 PDF 副本",
    Operation.DOCUMENT_CONTEXT_PACK: "AI 上下文包",
}


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


class DocumentSelectionView(QTreeWidget):
    files_added = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("documentList")
        self.setHeaderLabels(["文档", "类型", "大小", "位置"])
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.setMinimumHeight(132)
        self.setMaximumHeight(260)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.setAccessibleName("已选择的文档")
        self.setAccessibleDescription("文档名称、类型、大小和源文件夹")

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

    class _ListItemCompatibility:
        def __init__(self, item: QTreeWidgetItem) -> None:
            self._item = item

        def text(self) -> str:
            return str(self._item.data(0, Qt.ItemDataRole.UserRole))

    def item(self, row: int) -> _ListItemCompatibility | None:
        tree_item = self.topLevelItem(row)
        return self._ListItemCompatibility(tree_item) if tree_item is not None else None


class DocumentWorkspace(WorkspaceView):
    workspace_id = WorkspaceId.DOCUMENTS
    input_title = "添加文档"
    input_description = "PDF · Word · PowerPoint · Excel · HTML · TXT"
    input_accessible_description = "只接受文档格式；视频文件会建议转交视频工作区"

    def __init__(self, config: dict, tools: dict[str, ToolStatus], preview_registry) -> None:
        self._applying_preset = False
        self._pending_context_source_paths: tuple[Path, ...] = ()
        self._source_map_source_paths: tuple[Path, ...] = ()
        super().__init__(config, tools, DocumentWorkspaceController(tools), preview_registry)
        self.source_map_view.open_source_requested.connect(self._open_source_target)

    def _build_ui(self) -> None:
        page = QWidget()
        page.setObjectName("workspacePage")
        root = QVBoxLayout(page)
        self.page_layout = root
        root.setContentsMargins(30, 24, 34, 32)
        root.setSpacing(16)
        root.addWidget(self._create_hero())
        root.addWidget(self._create_input_panel())
        self.preparation_panel = self._create_options_panel()
        root.addWidget(self.preparation_panel)
        root.addWidget(self._create_summary())
        root.addWidget(self._create_state_panel())
        root.addWidget(self._create_recent_tasks())
        root.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.source_map_view = SourceMapView()
        self.source_map_view.back_requested.connect(self._close_source_map)
        self._source_map_pack_dir: Path | None = None
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(scroll)
        self.content_stack.addWidget(self.source_map_view)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.content_stack)
        self._render_input_paths()
        self.set_presentation_state(WorkspacePresentationState.EMPTY)

    def _create_hero(self) -> QWidget:
        hero = QFrame()
        hero.setObjectName("documentHero")
        layout = QHBoxLayout(hero)
        self.hero_layout = layout
        layout.setContentsMargins(24, 18, 18, 18)
        copy = QVBoxLayout()
        eyebrow = QLabel("DORO 文档  ·  仅保存在本机")
        eyebrow.setObjectName("documentEyebrow")
        title = QLabel("为 AI 准备文档")
        title.setObjectName("title")
        subtitle = QLabel("将 PDF、Office 文件和笔记整理为清晰、可用的输出，同时保持原文件不变。")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(subtitle)
        copy.addStretch()
        self.mascot_view = DocumentMascotView()
        self.mascot_view.setFixedWidth(170)
        layout.addLayout(copy, 1)
        layout.addWidget(self.mascot_view)
        return hero

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "page_layout"):
            return
        compact = self.width() < 720
        self.page_layout.setContentsMargins(
            14 if compact else 30,
            12 if compact else 24,
            14 if compact else 34,
            18 if compact else 32,
        )
        self.page_layout.setSpacing(12 if compact else 16)
        self.hero_layout.setContentsMargins(
            16 if compact else 24,
            14 if compact else 18,
            16 if compact else 18,
            14 if compact else 18,
        )
        self.mascot_view.setVisible(not compact)

    def _create_input_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("documentDropPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 20)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("文档")
        title.setObjectName("sectionTitle")
        self.selected_count = QLabel("未选择文档")
        self.selected_count.setObjectName("documentCount")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.selected_count)
        self.empty_guidance = QLabel(
            "将文档拖到这里，或从电脑中选择文件。\n选择文档后会显示下一步。"
        )
        self.empty_guidance.setObjectName("documentEmptyGuidance")
        self.empty_guidance.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_guidance.setWordWrap(True)
        self.input_description_label = QLabel(self.input_description)
        self.input_description_label.setObjectName("sectionDescription")
        self.input_description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.document_list = DocumentSelectionView()
        self.file_list = self.document_list
        actions = QGridLayout()
        actions.setHorizontalSpacing(8)
        actions.setVerticalSpacing(6)
        self.add_button = QPushButton("选择文件")
        self.add_button.setObjectName("documentChooseFiles")
        self.folder_button = QPushButton("选择文件夹")
        self.folder_button.setObjectName("secondary")
        self.remove_button = QPushButton("删除所选")
        self.remove_button.setObjectName("linkButton")
        self.clear_button = QPushButton("清空全部")
        self.clear_button.setObjectName("linkButton")
        self.reveal_button = QPushButton("打开源文件夹")
        self.reveal_button.setObjectName("linkButton")
        actions.setColumnStretch(0, 1)
        actions.setColumnStretch(3, 1)
        actions.addWidget(self.add_button, 0, 1)
        actions.addWidget(self.folder_button, 0, 2)
        actions.addWidget(self.remove_button, 1, 1)
        actions.addWidget(self.reveal_button, 1, 2)
        actions.addWidget(self.clear_button, 1, 3)
        layout.addLayout(header)
        layout.addWidget(self.empty_guidance)
        layout.addWidget(self.input_description_label)
        layout.addWidget(self.document_list)
        layout.addLayout(actions)
        self.add_button.clicked.connect(self._choose_files)
        self.folder_button.clicked.connect(self._choose_folder)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self.clear_inputs)
        self.reveal_button.clicked.connect(self._reveal_selected)
        self.document_list.files_added.connect(self.add_inputs)
        self.document_list.itemSelectionChanged.connect(self._selection_changed)
        return panel

    def _create_options_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("documentPreparation")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 20)
        layout.setSpacing(10)
        title = QLabel("处理设置")
        title.setObjectName("sectionTitle")
        description = QLabel("选择需要的输出格式，仅显示相关选项。")
        description.setObjectName("sectionDescription")
        layout.addWidget(title)
        layout.addWidget(description)

        preset_row = QHBoxLayout()
        preset_label = QLabel("准备用途")
        preset_label.setObjectName("fieldLabel")
        self.document_preset = QComboBox()
        self.document_preset.setMinimumWidth(220)
        self.document_preset.addItem("自定义 / 当前设置", None)
        for preset in DOCUMENT_PRESETS:
            self.document_preset.addItem(preset.label, preset.preset_id)
        self.document_preset.currentIndexChanged.connect(self._preset_changed)
        preset_row.addWidget(preset_label)
        preset_row.addWidget(self.document_preset, 1)
        layout.addLayout(preset_row)
        self.preset_note = QLabel("使用当前设置处理本次任务。")
        self.preset_note.setObjectName("documentModeDescription")
        self.preset_note.setWordWrap(True)
        layout.addWidget(self.preset_note)

        mode_row = QHBoxLayout()
        mode_label = QLabel("处理模式")
        mode_label.setObjectName("fieldLabel")
        self.operation = QComboBox()
        self.operation.setMinimumWidth(280)
        self.operation.currentIndexChanged.connect(self._operation_changed)
        self.operation.currentIndexChanged.connect(self._mark_preset_custom)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.operation, 1)
        layout.addLayout(mode_row)
        self.operation_description = QLabel()
        self.operation_description.setObjectName("documentModeDescription")
        self.operation_description.setWordWrap(True)
        layout.addWidget(self.operation_description)
        self.output_hint = QLabel()
        self.output_hint.setObjectName("outputHint")
        self.output_hint.setWordWrap(True)
        layout.addWidget(self.output_hint)

        self.tool_hint = QLabel()
        self.tool_hint.setObjectName("documentToolWarning")
        self.tool_hint.setWordWrap(True)
        self.setup_tool_button = QPushButton("打开文档设置")
        self.setup_tool_button.setObjectName("secondary")
        self.setup_tool_button.clicked.connect(
            lambda: self.settings_requested.emit(self.workspace_id.value)
        )
        tool_row = QHBoxLayout()
        tool_row.addWidget(self.tool_hint, 1)
        tool_row.addWidget(self.setup_tool_button)
        layout.addLayout(tool_row)

        self.basic_panel = QFrame()
        self.basic_panel.setObjectName("documentBasicOptions")
        basic = QVBoxLayout(self.basic_panel)
        basic.setContentsMargins(14, 12, 14, 12)
        basic_title = QLabel("本次任务")
        basic_title.setObjectName("fieldLabel")
        self.document_mode = QComboBox()
        self.document_mode.addItem("清理结构并准备 AI 使用", "enhanced")
        self.document_mode.addItem("保留直接 MarkItDown 转换", "raw")
        self.document_mode.setCurrentIndex(
            1 if str(self.config["document"]["mode"]) == "raw" else 0
        )
        self.document_mode.currentIndexChanged.connect(self._operation_changed)
        self.document_mode.currentIndexChanged.connect(self._mark_preset_custom)
        self.split_document = QCheckBox("将长内容拆分为易于处理的章节")
        self.split_document.setChecked(bool(self.config["document"]["split_enabled"]))
        self.split_document.stateChanged.connect(self._split_changed)
        self.split_document.stateChanged.connect(self._mark_preset_custom)
        self.ocr_enabled = QCheckBox("使用本地 OCR 识别扫描页和内嵌图片")
        self.ocr_enabled.setChecked(bool(self.config["document"]["ocr_enabled"]))
        self.ocr_enabled.stateChanged.connect(self._update_summary)
        self.ocr_enabled.stateChanged.connect(self._mark_preset_custom)
        self.context_budget_panel = QFrame()
        self.context_budget_panel.setObjectName("contextBudgetPanel")
        budget_layout = QVBoxLayout(self.context_budget_panel)
        budget_layout.setContentsMargins(0, 8, 0, 4)
        budget_label = QLabel("上下文预算")
        budget_label.setObjectName("fieldLabel")
        budget_note = QLabel("使用与模型无关的令牌估算。不会为了满足预算而主动删除内容。")
        budget_note.setObjectName("sectionDescription")
        budget_note.setWordWrap(True)
        self.context_budget = QComboBox()
        self.context_budget.addItem("不限", None)
        self.context_budget.addItem("32K", 32000)
        self.context_budget.addItem("64K", 64000)
        self.context_budget.addItem("128K", 128000)
        self.context_budget.addItem("自定义", "custom")
        self.context_budget.currentIndexChanged.connect(self._budget_changed)
        self.context_budget.currentIndexChanged.connect(self._mark_preset_custom)
        self.custom_budget = QSpinBox()
        self.custom_budget.setRange(1000, 10000000)
        self.custom_budget.setSingleStep(1000)
        self.custom_budget.setSuffix(" 估算令牌")
        configured_budget = self.config["document"].get("context_pack_default_budget")
        if isinstance(configured_budget, int) and not isinstance(configured_budget, bool):
            preset_index = self.context_budget.findData(configured_budget)
            if preset_index >= 0:
                self.context_budget.setCurrentIndex(preset_index)
            else:
                self.context_budget.setCurrentIndex(self.context_budget.findData("custom"))
                self.custom_budget.setValue(configured_budget)
        else:
            self.custom_budget.setValue(100000)
        self.custom_budget.valueChanged.connect(self._update_summary)
        self.custom_budget.valueChanged.connect(self._mark_preset_custom)
        budget_layout.addWidget(budget_label)
        budget_layout.addWidget(self.context_budget)
        budget_layout.addWidget(self.custom_budget)
        budget_layout.addWidget(budget_note)
        basic.addWidget(basic_title)
        basic.addWidget(self.document_mode)
        basic.addWidget(self.split_document)
        basic.addWidget(self.ocr_enabled)
        basic.addWidget(self.context_budget_panel)

        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("默认：每个源文件旁的 AI素材处理结果 文件夹")
        self.output_path.textChanged.connect(self._update_summary)
        output_button = QPushButton("选择…")
        output_button.setObjectName("secondary")
        output_button.clicked.connect(self._choose_output)
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出"))
        output_row.addWidget(self.output_path, 1)
        output_row.addWidget(output_button)
        basic.addLayout(output_row)
        layout.addWidget(self.basic_panel)

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setObjectName("documentAdvancedToggle")
        self.advanced_toggle.setText("高级选项")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.toggled.connect(self._advanced_toggled)
        layout.addWidget(self.advanced_toggle)
        self.advanced_panel = QFrame()
        self.advanced_panel.setObjectName("documentAdvancedOptions")
        advanced = QVBoxLayout(self.advanced_panel)
        advanced.setContentsMargins(14, 10, 14, 12)
        target_label = QLabel("目标章节长度")
        target_label.setObjectName("fieldLabel")
        self.target_tokens = QSpinBox()
        self.target_tokens.setRange(500, 100000)
        self.target_tokens.setSingleStep(500)
        self.target_tokens.setSuffix(" 估算令牌 / 章节")
        self.target_tokens.setValue(int(self.config["document"]["target_tokens"]))
        self.target_tokens.valueChanged.connect(self._mark_preset_custom)
        technical_note = QLabel("令牌数值仅为估算，不会为了满足该长度而静默删除内容。")
        technical_note.setObjectName("sectionDescription")
        technical_note.setWordWrap(True)
        advanced.addWidget(target_label)
        advanced.addWidget(self.target_tokens)
        advanced.addWidget(technical_note)
        self.advanced_panel.setVisible(False)
        self.custom_budget.setVisible(self.context_budget.currentData() == "custom")
        layout.addWidget(self.advanced_panel)
        return panel

    def _create_summary(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("documentSummary")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 16, 22, 18)
        title = QLabel("准备就绪")
        title.setObjectName("sectionTitle")
        details = QGridLayout()
        details.setHorizontalSpacing(14)
        details.setVerticalSpacing(6)
        self.summary_count = QLabel("添加文档后继续")
        self.summary_count.setObjectName("documentSummaryValue")
        self.summary_mode = QLabel("—")
        self.summary_mode.setObjectName("documentSummaryValue")
        self.summary_ocr = QLabel("OCR：—")
        self.summary_ocr.setObjectName("documentSummaryValue")
        self.summary_budget = QLabel()
        self.summary_budget.setObjectName("documentSummaryValue")
        self.summary_output = QLabel("输出：—")
        self.summary_output.setObjectName("documentSummaryValue")
        self.summary_output.setWordWrap(True)
        details.addWidget(self.summary_count, 0, 0)
        details.addWidget(self.summary_mode, 0, 1)
        details.addWidget(self.summary_ocr, 1, 0)
        details.addWidget(self.summary_budget, 1, 1)
        details.setColumnStretch(2, 1)
        actions = QHBoxLayout()
        self.preview_button = QPushButton("预览文档处理方案")
        self.preview_button.setObjectName("secondary")
        self.preview_button.clicked.connect(self._show_preview)
        self.start_button = QPushButton("准备文档")
        self.start_button.setObjectName("documentPrimary")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self._request_jobs)
        actions.addStretch()
        actions.addWidget(self.preview_button)
        actions.addWidget(self.start_button)
        layout.addWidget(title)
        layout.addLayout(details)
        layout.addWidget(self.summary_output)
        layout.addLayout(actions)
        return panel

    def _create_state_panel(self) -> QWidget:
        self.state_panel = QFrame()
        self.state_panel.setObjectName("documentState")
        layout = QVBoxLayout(self.state_panel)
        layout.setContentsMargins(22, 15, 22, 17)
        header = QHBoxLayout()
        self.state_heading = QLabel()
        self.state_heading.setObjectName("sectionTitle")
        self.state_badge = QLabel()
        self.state_badge.setObjectName("documentStateBadge")
        header.addWidget(self.state_heading)
        header.addStretch()
        header.addWidget(self.state_badge)
        self.state_message = QLabel()
        self.state_message.setObjectName("sectionDescription")
        self.state_message.setWordWrap(True)
        self.workspace_progress = QProgressBar()
        self.workspace_progress.setValue(0)
        self.result_heading = QLabel()
        self.result_heading.setObjectName("documentResultHeading")
        self.result_details = QLabel()
        self.result_details.setObjectName("documentResultDetails")
        self.result_details.setWordWrap(True)
        self.technical_details_button = QPushButton("查看技术详情")
        self.technical_details_button.setObjectName("linkButton")
        self.technical_details_button.clicked.connect(self._show_technical_details)
        self.open_button = QPushButton("打开输出")
        self.open_button.setObjectName("secondary")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(
            lambda: (
                self.open_output_requested.emit(self.last_outputs[0]) if self.last_outputs else None
            )
        )
        self.report_button = QPushButton("查看上下文报告")
        self.report_button.setObjectName("secondary")
        self.report_button.setVisible(False)
        self.report_button.clicked.connect(self._open_context_report)
        self.source_map_button = QPushButton("查看来源地图")
        self.source_map_button.setObjectName("secondary")
        self.source_map_button.setVisible(False)
        self.source_map_button.setAccessibleName("查看来源地图")
        self.source_map_button.clicked.connect(self._open_source_map)
        self.copy_for_ai_button = QPushButton("复制给 AI")
        self.copy_for_ai_button.setObjectName("secondary")
        self.copy_for_ai_button.setVisible(False)
        self.copy_for_ai_button.setAccessibleName("复制给 AI")
        self.copy_for_ai_button.clicked.connect(self._copy_for_ai)
        result_actions = QGridLayout()
        result_actions.setHorizontalSpacing(8)
        result_actions.setVerticalSpacing(6)
        result_actions.addWidget(self.result_heading, 0, 0, 1, 2)
        result_actions.addWidget(self.technical_details_button, 1, 0)
        result_actions.addWidget(self.report_button, 1, 1)
        result_actions.addWidget(self.source_map_button, 2, 0)
        result_actions.addWidget(self.copy_for_ai_button, 2, 1)
        result_actions.addWidget(self.open_button, 3, 0, 1, 2)
        result_actions.setColumnStretch(0, 1)
        result_actions.setColumnStretch(1, 1)
        layout.addLayout(header)
        layout.addWidget(self.state_message)
        layout.addWidget(self.workspace_progress)
        layout.addLayout(result_actions)
        layout.addWidget(self.result_details)
        self.state_label = self.state_message
        self._technical_details = ""
        return self.state_panel

    def _create_recent_tasks(self) -> QWidget:
        recent = QFrame()
        recent.setObjectName("workspaceRecent")
        layout = QVBoxLayout(recent)
        header = QHBoxLayout()
        title = QLabel("最近的文档任务")
        title.setObjectName("sectionTitle")
        self.history_button = QPushButton("查看文档历史")
        self.history_button.setObjectName("linkButton")
        self.history_button.clicked.connect(
            lambda: self.history_requested.emit(self.workspace_id.value)
        )
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.history_button)
        self.recent_tasks = QTableWidget(0, 4)
        self.recent_tasks.setHorizontalHeaderLabels(["来源", "处理方式", "结果", "进度"])
        self.recent_tasks.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.recent_tasks.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.recent_tasks.verticalHeader().setVisible(False)
        self.recent_tasks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.recent_tasks.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.recent_tasks.setMinimumHeight(150)
        layout.addLayout(header)
        layout.addWidget(self.recent_tasks)
        return recent

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择文档",
            "",
            "文档 (*.pdf *.doc *.docx *.ppt *.pptx *.xls *.xlsx *.html *.htm *.txt *.csv *.json *.xml *.md);;所有文件 (*)",
        )
        self.add_inputs(paths)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择文档文件夹")
        if path:
            self.add_inputs([path])

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择文档输出文件夹")
        if path:
            self.output_path.setText(path)

    def _render_input_paths(self) -> None:
        self.document_list.clear()
        for path in self.paths:
            try:
                size = _human_size(path.stat().st_size)
            except OSError:
                size = "不可用"
            item = QTreeWidgetItem(
                [path.name, path.suffix.upper().lstrip(".") or "文件", size, str(path.parent)]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(0, str(path))
            item.setToolTip(3, str(path.parent))
            self.document_list.addTopLevelItem(item)
        count = len(self.paths)
        self.selected_count.setText("未选择文档" if count == 0 else f"已选择 {count} 个文档")
        self.empty_guidance.setVisible(not self.paths)
        self.input_description_label.setVisible(not self.paths)
        self.document_list.setVisible(bool(self.paths))
        self.remove_button.setVisible(bool(self.paths))
        self.reveal_button.setVisible(bool(self.paths))
        self.clear_button.setVisible(bool(self.paths))
        self.preparation_panel.setVisible(bool(self.paths))
        self._selection_changed()
        self._update_summary()

    def _selection_changed(self) -> None:
        selected = bool(self.document_list.selectedItems())
        self.remove_button.setEnabled(selected)
        self.reveal_button.setEnabled(selected)

    def _remove_selected(self) -> None:
        selected = {
            str(item.data(0, Qt.ItemDataRole.UserRole)).casefold()
            for item in self.document_list.selectedItems()
        }
        if not selected:
            return
        self.paths = [path for path in self.paths if str(path).casefold() not in selected]
        self._render_input_paths()
        self.refresh_operations()
        self.set_presentation_state(
            WorkspacePresentationState.INPUTS_SELECTED
            if self.paths
            else WorkspacePresentationState.EMPTY
        )

    def _reveal_selected(self) -> None:
        selected = self.document_list.selectedItems()
        if not selected:
            return
        path = Path(str(selected[0].data(0, Qt.ItemDataRole.UserRole)))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def refresh_operations(self) -> None:
        previous = self.operation.currentData()
        availability = self.controller.operation_availability(self.paths)
        self.operation.blockSignals(True)
        self.operation.clear()
        model = self.operation.model()
        assert isinstance(model, QStandardItemModel)
        for option in availability:
            self.operation.addItem(self._operation_label(option.operation), option.operation.value)
            item = model.item(self.operation.count() - 1)
            item.setEnabled(option.available)
            item.setToolTip(option.reason)
            item.setData(option.reason, Qt.ItemDataRole.UserRole + 1)
        if previous is not None:
            index = self.operation.findData(previous)
            if index >= 0:
                self.operation.setCurrentIndex(index)
        self.operation.blockSignals(False)
        self._refresh_preset_availability(availability)
        self._operation_changed()

    def _refresh_preset_availability(
        self, availability: list[DocumentOperationAvailability]
    ) -> None:
        available_by_operation = {option.operation: option for option in availability}
        model = self.document_preset.model()
        assert isinstance(model, QStandardItemModel)
        for preset in DOCUMENT_PRESETS:
            index = self.document_preset.findData(preset.preset_id)
            item = model.item(index)
            option = available_by_operation.get(preset.operation)
            enabled = option is not None and option.available
            item.setEnabled(enabled)
            item.setToolTip(
                ""
                if enabled
                else option.reason
                if option is not None and option.reason
                else "请添加兼容的文档以使用此预设。"
            )
        current_id = self.document_preset.currentData()
        if current_id is not None:
            current_item = model.item(self.document_preset.currentIndex())
            if not current_item.isEnabled():
                self.document_preset.setCurrentIndex(0)

    def _preset_changed(self) -> None:
        preset_id = self.document_preset.currentData()
        if preset_id is None:
            self.preset_note.setText("使用当前设置处理本次任务。")
            return
        preset = PRESET_BY_ID[str(preset_id)]
        operation_index = self.operation.findData(preset.operation.value)
        operation_model = self.operation.model()
        assert isinstance(operation_model, QStandardItemModel)
        if operation_index < 0 or not operation_model.item(operation_index).isEnabled():
            self.preset_note.setText("此预设不适用于所选文档或当前已安装的工具。")
            return
        self._applying_preset = True
        try:
            self.operation.setCurrentIndex(operation_index)
            budget_index = self.context_budget.findData(preset.context_budget)
            if budget_index >= 0:
                self.context_budget.setCurrentIndex(budget_index)
            ocr_available = self.tools.get("rapidocr", ToolStatus("rapidocr", None)).available
            self.ocr_enabled.setChecked(preset.ocr_enabled and ocr_available)
        finally:
            self._applying_preset = False
        note = preset.description
        if preset.ocr_enabled and not self.ocr_enabled.isChecked():
            note += " 本地 OCR 不可用；本次任务将不使用 OCR。"
        self.preset_note.setText(note)
        self._update_summary()

    def _mark_preset_custom(self) -> None:
        if self._applying_preset or not hasattr(self, "document_preset"):
            return
        if self.document_preset.currentData() is not None:
            self.document_preset.setCurrentIndex(0)

    def _selected_availability(self) -> DocumentOperationAvailability | None:
        raw = self.operation.currentData()
        if raw is None:
            return None
        operation = Operation(raw)
        return next(
            (
                option
                for option in self.controller.operation_availability(self.paths)
                if option.operation is operation
            ),
            None,
        )

    def _operation_label(self, operation: Operation) -> str:
        if operation is Operation.TO_MARKDOWN and hasattr(self, "document_mode"):
            return (
                "AI 就绪 Markdown"
                if self.document_mode.currentData() == "enhanced"
                else "转换为 Markdown"
            )
        return _OPERATION_LABELS[operation]

    def _operation_changed(self) -> None:
        raw = self.operation.currentData()
        operation = Operation(raw) if raw is not None else None
        markdown = operation is Operation.TO_MARKDOWN
        context_pack = operation is Operation.DOCUMENT_CONTEXT_PACK
        enhanced = markdown and self.document_mode.currentData() == "enhanced"
        if markdown and self.operation.currentIndex() >= 0:
            self.operation.setItemText(
                self.operation.currentIndex(), self._operation_label(Operation.TO_MARKDOWN)
            )
        self.document_mode.setVisible(markdown)
        self.split_document.setVisible(enhanced)
        self.ocr_enabled.setVisible(enhanced or context_pack)
        self.context_budget_panel.setVisible(context_pack)
        self.advanced_toggle.setVisible(enhanced)
        if not enhanced:
            self.advanced_toggle.setChecked(False)
        self.target_tokens.setEnabled(enhanced and self.split_document.isChecked())
        option = self._selected_availability()
        reason = option.reason if option is not None and not option.available else ""
        self.tool_hint.setText(reason)
        self.tool_hint.setVisible(bool(reason))
        self.setup_tool_button.setVisible(bool(reason))
        ocr_available = self.tools.get("rapidocr", ToolStatus("rapidocr", None)).available
        self.ocr_enabled.setEnabled(ocr_available)
        self.ocr_enabled.setToolTip(
            "" if ocr_available else "本地 OCR 不可用，请在文档设置中完成配置。"
        )
        if markdown and enhanced:
            self.operation_description.setText(
                "清理结构，运行现有质量检查，并可选地拆分长内容，同时保留来源信息。"
            )
            self.output_hint.setText("输出：现有 AI 资料包格式。")
        elif context_pack:
            self.operation_description.setText(
                "将一个或多个文档组合为可追溯的上传包，并提供确定性的上下文预算和完整性报告。"
            )
            self.output_hint.setText(
                "输出：START_HERE、完整内容归档、编号分包、来源包、manifest 和上下文报告。"
            )
        elif markdown:
            self.operation_description.setText("保留直接 MarkItDown 转换，不进行增强清理或拆分。")
            self.output_hint.setText("输出：单个 Markdown 文件。")
        elif operation is Operation.TO_PDF:
            self.operation_description.setText(
                "使用 Microsoft Office 或 LibreOffice 创建 PDF 副本，源文件不会改变。"
            )
            self.output_hint.setText("输出：单个 PDF 文件。")
        else:
            self.operation_description.setText("选择文档后查看可用的处理模式。")
            self.output_hint.setText("添加文档后查看输出格式。")
        can_start = bool(self.paths and option is not None and option.available)
        self.start_button.setEnabled(can_start)
        self.preview_button.setEnabled(can_start)
        self.start_button.setToolTip(reason)
        self.preview_button.setToolTip(reason)
        self._update_summary()

    def _budget_changed(self) -> None:
        self.custom_budget.setVisible(self.context_budget.currentData() == "custom")
        self._update_summary()

    def _context_budget_value(self) -> int | None:
        value = self.context_budget.currentData()
        return self.custom_budget.value() if value == "custom" else value

    def _advanced_toggled(self, checked: bool) -> None:
        self.advanced_panel.setVisible(checked)
        self.advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )

    def _split_changed(self) -> None:
        self.target_tokens.setEnabled(self.split_document.isChecked())
        self._update_summary()

    def _update_summary(self) -> None:
        if not hasattr(self, "summary_count"):
            return
        count = len(self.paths)
        self.summary_count.setText("添加文档后继续" if count == 0 else f"{count} 个文档")
        raw = self.operation.currentData()
        self.summary_mode.setText(
            self._operation_label(Operation(raw)) if raw is not None else "没有兼容的模式"
        )
        enhanced = (
            raw == Operation.TO_MARKDOWN.value and self.document_mode.currentData() == "enhanced"
        )
        ocr = enhanced and self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
        self.summary_ocr.setText("OCR：开启" if ocr else "OCR：关闭")
        context_pack = raw == Operation.DOCUMENT_CONTEXT_PACK.value
        self.summary_budget.setVisible(context_pack)
        if context_pack:
            budget = self._context_budget_value()
            self.summary_ocr.setText(
                "OCR：开启"
                if self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
                else "OCR：关闭"
            )
            self.summary_budget.setText(
                f"上下文预算：{budget:,} 个估算令牌" if budget else "上下文预算：不限"
            )
        if self.output_path.text().strip():
            output = self.output_path.text().strip()
        elif self.paths:
            output = str(self.output_for(self.paths[0]))
        else:
            output = "每个源文件旁"
        self.summary_output.setText(f"输出：{output}")

    def _parameters(self) -> dict[str, object]:
        if self.operation.currentData() == Operation.DOCUMENT_CONTEXT_PACK.value:
            budget = self._context_budget_value()
            return {
                "来源数量": len(self.paths),
                "上下文预算": f"{budget:,} 个估算令牌" if budget else "不限",
                "预计上下文": "预处理后可用",
                "OCR": "开启"
                if self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
                else "关闭",
                "完整性": "不会主动删除任何内容",
            }
        enhanced = self.document_mode.currentData() == "enhanced"
        return {
            "模式": "AI 增强" if enhanced else "原始转换",
            "自动拆分": "是" if enhanced and self.split_document.isChecked() else "否",
            "目标长度": f"{self.target_tokens.value()} 个估算令牌",
            "OCR": "开启"
            if enhanced and self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
            else "关闭",
        }

    def _show_preview(self) -> None:
        option = self._selected_availability()
        if not self.paths or option is None or not option.available:
            return
        request = PreviewRequest(
            tuple(self.paths), option.operation, self.output_for(self.paths[0]), self._parameters()
        )
        try:
            self.preview_ready.emit(self.preview_registry.build(request))
            self.set_presentation_state(WorkspacePresentationState.PREVIEW)
        except Exception as exc:
            self._technical_details = str(exc)
            self.set_presentation_state(WorkspacePresentationState.ERROR, "无法创建预览。")
            QMessageBox.critical(self, "无法预览", str(exc))

    def _request_jobs(self) -> None:
        option = self._selected_availability()
        if not self.paths or option is None or not option.available:
            return
        self.config["document"]["mode"] = str(self.document_mode.currentData())
        self.config["document"]["split_enabled"] = self.split_document.isChecked()
        self.config["document"]["target_tokens"] = self.target_tokens.value()
        self.config["document"]["max_tokens"] = max(
            self.target_tokens.value() + 1000,
            int(self.config["document"].get("max_tokens", 6000)),
        )
        self.config["document"]["ocr_enabled"] = (
            self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
        )
        context_budget = (
            self._context_budget_value()
            if option.operation is Operation.DOCUMENT_CONTEXT_PACK
            else None
        )
        if option.operation is Operation.DOCUMENT_CONTEXT_PACK:
            self.config["document"]["context_pack_default_budget"] = context_budget
        jobs = self.controller.create_jobs(
            self.paths,
            option.operation,
            self.output_for,
            context_budget=context_budget,
            context_ocr_enabled=(
                self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
                if option.operation is Operation.DOCUMENT_CONTEXT_PACK
                else None
            ),
        )
        self._pending_context_source_paths = (
            tuple(jobs[0].input_sources)
            if jobs and option.operation is Operation.DOCUMENT_CONTEXT_PACK
            else ()
        )
        self._reset_source_map()
        self.jobs_requested.emit(self.workspace_id.value, jobs)

    def set_presentation_state(
        self, state: WorkspacePresentationState, message: str | None = None
    ) -> None:
        self.presentation_state = state
        defaults = {
            WorkspacePresentationState.EMPTY: (
                "添加文档",
                "等待中",
                "选择文件以开始。",
            ),
            WorkspacePresentationState.INPUTS_SELECTED: (
                "准备就绪",
                "就绪",
                f"已选择 {len(self.paths)} 个文档。",
            ),
            WorkspacePresentationState.PREVIEW: (
                "预览已准备",
                "尚未开始",
                "请检查预览，确认后再准备文档。",
            ),
            WorkspacePresentationState.PROCESSING: (
                "正在处理文档",
                f"{self.workspace_progress.value()}%",
                "切换工作区不会取消当前任务。",
            ),
            WorkspacePresentationState.SUCCESS: (
                "文档已准备好",
                "完成",
                "原文件未被修改。",
            ),
            WorkspacePresentationState.WARNING: (
                "文档已准备好，但有提醒",
                "请检查结果",
                "部分项目需要注意，已完成的输出仍然可用。",
            ),
            WorkspacePresentationState.ERROR: (
                "处理已停止",
                "未完成",
                "原文件未被修改。",
            ),
        }
        heading, badge, default_message = defaults[state]
        self.state_heading.setText(heading)
        self.state_badge.setText(badge)
        self.state_message.setText(message or default_message)
        self.state_panel.setObjectName(
            "documentStateWarning"
            if state is WorkspacePresentationState.WARNING
            else "documentStateError"
            if state is WorkspacePresentationState.ERROR
            else "documentState"
        )
        self.state_panel.style().unpolish(self.state_panel)
        self.state_panel.style().polish(self.state_panel)
        mascot_state = {
            WorkspacePresentationState.EMPTY: (
                DocumentMascotState.COMPLETED if self.last_outputs else DocumentMascotState.EMPTY
            ),
            WorkspacePresentationState.INPUTS_SELECTED: DocumentMascotState.READY,
            WorkspacePresentationState.PREVIEW: DocumentMascotState.PREVIEW,
            WorkspacePresentationState.PROCESSING: DocumentMascotState.PROCESSING,
            WorkspacePresentationState.SUCCESS: DocumentMascotState.SUCCESS,
            WorkspacePresentationState.WARNING: DocumentMascotState.WARNING,
            WorkspacePresentationState.ERROR: DocumentMascotState.ERROR,
        }[state]
        self.mascot_view.set_state(mascot_state)
        result_state = state in {
            WorkspacePresentationState.SUCCESS,
            WorkspacePresentationState.WARNING,
        }
        self.result_heading.setVisible(result_state)
        self.result_details.setVisible(result_state)
        self.technical_details_button.setVisible(
            state in {WorkspacePresentationState.WARNING, WorkspacePresentationState.ERROR}
            and bool(self._technical_details)
        )
        self.workspace_progress.setVisible(state is WorkspacePresentationState.PROCESSING)
        self.setProperty("presentationState", state.value)

    def set_progress(self, value: int, message: str) -> None:
        self.workspace_progress.setValue(value)
        self.set_presentation_state(WorkspacePresentationState.PROCESSING, message)
        self.state_heading.setText(f"正在处理文档 · {value}%")

    def set_completed(
        self,
        outputs: list[str],
        errors: list[str],
        quality_reports: list[dict] | None = None,
    ) -> None:
        self._reset_source_map()
        self.last_outputs = outputs
        self.open_button.setEnabled(bool(outputs))
        self.workspace_progress.setValue(
            100 if outputs and not errors else self.workspace_progress.value()
        )
        self._technical_details = "\n".join(errors)
        context_report = next(
            (
                report
                for report in (quality_reports or [])
                if report.get("context_pack_version") == 1
            ),
            None,
        )
        self._source_map_pack_dir = Path(outputs[0]) if (context_report and outputs) else None
        if self._source_map_pack_dir is not None:
            self._source_map_source_paths = self._pending_context_source_paths or tuple(self.paths)
        else:
            self._source_map_source_paths = ()
        self._pending_context_source_paths = ()
        self.report_button.setVisible(self._source_map_pack_dir is not None)
        self.source_map_button.setVisible(self._source_map_pack_dir is not None)
        self.copy_for_ai_button.setVisible(self._source_map_pack_dir is not None)
        summary: ContextPackSummary | None = None
        if self._source_map_pack_dir is not None:
            try:
                summary = summarize_context_pack(self._source_map_pack_dir)
            except (OSError, ValueError):
                summary = None
        overflow = summary.overflow_count if summary is not None else 0
        report_unavailable = summary is not None and not summary.report_available
        report_warnings = bool(summary and summary.warnings)
        state = (
            WorkspacePresentationState.WARNING
            if outputs and (errors or overflow or report_warnings or report_unavailable)
            else WorkspacePresentationState.SUCCESS
            if outputs
            else WorkspacePresentationState.ERROR
        )
        if summary is not None and summary.report_available:
            self.result_heading.setText("AI 上下文包已准备好")
            self.result_details.setText(self._format_summary(summary))
        elif summary is not None:
            self.result_heading.setText("AI 上下文包需要检查")
            self.result_details.setText(
                "输出已创建，但 context-report.json 缺失或无效。\n请打开上下文包检查可用文件。"
            )
        else:
            self.result_heading.setText(f"已创建 {len(outputs)} 个输出")
            self.result_details.setText(
                "\n".join(outputs[:4]) + ("\n…" if len(outputs) > 4 else "")
            )
        self.set_presentation_state(
            state,
            "上下文包输出已创建，但无法验证 context-report.json。"
            if report_unavailable
            else f"上下文包已创建，其中有 {overflow} 个分包超过预算。未删除任何内容。"
            if overflow
            else f"上下文包已创建，其中有 {len(summary.warnings)} 条提醒。请检查结果。"
            if summary is not None and summary.warnings
            else f"已完成 {len(outputs)} 个输出；有 {len(errors)} 个需要注意。"
            if errors
            else f"已完成 {len(outputs)} 个输出。原文件未被修改。",
        )

    def _format_summary(self, summary: ContextPackSummary) -> str:
        lines = [
            f"来源：{summary.source_count} 个",
            f"上下文包：{summary.pack_count} 个",
            f"估算令牌：约 {summary.estimated_tokens:,} 个",
            "",
            f"预算：{self._summary_budget_label(summary)}",
            "",
            f"完整性："
            f"{'✓ 所有内容块均已保留' if summary.integrity_ok else '不完整：部分内容块缺失或未验证'}",
        ]
        if summary.warnings:
            lines.extend(("", "提醒："))
            for warning in summary.warnings:
                code = str(warning.get("code") or "")
                detail = (
                    {
                        "context_pack_over_budget": "某个内容块无法安全拆分，因此对应分包超出预算。",
                        "privacy_path_redacted": "已从输出中移除私有文件路径。",
                    }.get(code)
                    or warning.get("reason")
                    or warning.get("message")
                    or code
                    or "未知提醒"
                )
                lines.append(f"- {detail}")
        return "\n".join(lines)

    @staticmethod
    def _summary_budget_label(summary: ContextPackSummary) -> str:
        label = summary.budget_label
        if label == "No limit":
            return "不限"
        if label.endswith(" context window"):
            return f"{label.removesuffix(' context window')} 上下文窗口"
        return label.replace(" estimated tokens", " 预计 tokens")

    def _open_context_report(self) -> None:
        if not self.last_outputs:
            return
        report = Path(self.last_outputs[0]) / "context-report.json"
        if report.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(report)))

    def _open_source_map(self) -> None:
        if self._source_map_pack_dir is None:
            return
        try:
            source_map = self.controller.load_source_map(self._source_map_pack_dir)
        except (OSError, ValueError) as exc:
            self.source_map_view.set_source_map(None)
            QMessageBox.critical(self, "来源地图不可用", str(exc))
            return
        self.source_map_view.set_source_map(
            source_map,
            source_paths_by_id(source_map.sources, self._source_map_source_paths),
        )
        self.content_stack.setCurrentWidget(self.source_map_view)

    def _open_source_target(self, target: SourceOpenTarget) -> None:
        if not target.available or target.path is None:
            QMessageBox.information(self, "来源不可用", target.reason)
            return
        url = QUrl.fromLocalFile(str(target.path))
        if target.capability is SourceOpenCapability.PAGE_LEVEL and target.page is not None:
            url.setFragment(f"page={target.page}")
            if QDesktopServices.openUrl(url):
                return
            url = QUrl.fromLocalFile(str(target.path))
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self,
                "无法打开来源",
                "Windows 无法使用关联的应用打开此来源。",
            )

    def _reset_source_map(self) -> None:
        self._source_map_pack_dir = None
        self._source_map_source_paths = ()
        self.source_map_button.setVisible(False)
        self.copy_for_ai_button.setVisible(False)
        self.copy_for_ai_button.setText("复制给 AI")
        self.source_map_view.set_source_map(None)
        self.content_stack.setCurrentIndex(0)

    def _close_source_map(self) -> None:
        self.content_stack.setCurrentIndex(0)

    def _copy_for_ai(self) -> None:
        if self._source_map_pack_dir is None:
            return
        try:
            text = build_context_copy(self._source_map_pack_dir)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "无法复制给 AI", str(exc))
            return
        QApplication.clipboard().setText(text)
        self.copy_for_ai_button.setText("已复制 ✓")
        QTimer.singleShot(2000, lambda: self.copy_for_ai_button.setText("复制给 AI"))

    def _show_technical_details(self) -> None:
        if self._technical_details:
            QMessageBox.information(self, "技术详情", self._technical_details)
