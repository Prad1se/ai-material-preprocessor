from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
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
from ...apps.documents.workspace_controller import (
    DocumentOperationAvailability,
    DocumentWorkspaceController,
)
from ...models import Operation, ToolStatus
from ..document_mascot import DocumentMascotState, DocumentMascotView
from ..source_map_view import SourceMapView
from .common import WorkspacePresentationState, WorkspaceView

_OPERATION_LABELS = {
    Operation.TO_MARKDOWN: "AI-ready Markdown",
    Operation.TO_PDF: "Create a PDF copy",
    Operation.DOCUMENT_CONTEXT_PACK: "AI Context Pack",
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
        self.setHeaderLabels(["Document", "Type", "Size", "Location"])
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
        self.setAccessibleName("Selected documents")
        self.setAccessibleDescription("Document name, type, size, and source folder")

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
    input_title = "Add documents"
    input_description = "PDF · Word · PowerPoint · Excel · HTML · TXT"
    input_accessible_description = "只接受文档格式；视频会建议转交 Video Workspace"

    def __init__(self, config: dict, tools: dict[str, ToolStatus], preview_registry) -> None:
        super().__init__(config, tools, DocumentWorkspaceController(tools), preview_registry)

    def _build_ui(self) -> None:
        page = QWidget()
        page.setObjectName("workspacePage")
        root = QVBoxLayout(page)
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
        layout.setContentsMargins(24, 18, 18, 18)
        copy = QVBoxLayout()
        eyebrow = QLabel("DORO DOCUMENTS  ·  PRIVATE ON THIS DEVICE")
        eyebrow.setObjectName("documentEyebrow")
        title = QLabel("Prepare documents for AI")
        title.setObjectName("title")
        subtitle = QLabel(
            "Turn PDFs, Office files and notes into clean, usable outputs while keeping the "
            "originals untouched."
        )
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

    def _create_input_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("documentDropPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 20)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("Documents")
        title.setObjectName("sectionTitle")
        self.selected_count = QLabel("No documents selected")
        self.selected_count.setObjectName("documentCount")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.selected_count)
        self.empty_guidance = QLabel(
            "Drop documents here, or choose files from your computer.\n"
            "The next step appears after your documents are selected."
        )
        self.empty_guidance.setObjectName("documentEmptyGuidance")
        self.empty_guidance.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_guidance.setWordWrap(True)
        self.input_description_label = QLabel(self.input_description)
        self.input_description_label.setObjectName("sectionDescription")
        self.input_description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.document_list = DocumentSelectionView()
        self.file_list = self.document_list
        actions = QHBoxLayout()
        self.add_button = QPushButton("Choose files")
        self.add_button.setObjectName("documentChooseFiles")
        self.folder_button = QPushButton("Choose folder")
        self.folder_button.setObjectName("secondary")
        self.remove_button = QPushButton("Remove selected")
        self.remove_button.setObjectName("linkButton")
        self.clear_button = QPushButton("Clear all")
        self.clear_button.setObjectName("linkButton")
        self.reveal_button = QPushButton("Open source folder")
        self.reveal_button.setObjectName("linkButton")
        actions.addStretch()
        actions.addWidget(self.add_button)
        actions.addWidget(self.folder_button)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.reveal_button)
        actions.addWidget(self.clear_button)
        actions.addStretch()
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
        title = QLabel("Preparation")
        title.setObjectName("sectionTitle")
        description = QLabel("Choose the output you need. Only relevant options are shown.")
        description.setObjectName("sectionDescription")
        layout.addWidget(title)
        layout.addWidget(description)

        mode_row = QHBoxLayout()
        mode_label = QLabel("Processing mode")
        mode_label.setObjectName("fieldLabel")
        self.operation = QComboBox()
        self.operation.setMinimumWidth(280)
        self.operation.currentIndexChanged.connect(self._operation_changed)
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
        self.setup_tool_button = QPushButton("Open Documents Settings")
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
        basic_title = QLabel("For this job")
        basic_title.setObjectName("fieldLabel")
        self.document_mode = QComboBox()
        self.document_mode.addItem("Clean structure and prepare for AI", "enhanced")
        self.document_mode.addItem("Keep the direct MarkItDown conversion", "raw")
        self.document_mode.setCurrentIndex(
            1 if str(self.config["document"]["mode"]) == "raw" else 0
        )
        self.document_mode.currentIndexChanged.connect(self._operation_changed)
        self.split_document = QCheckBox("Split long content into manageable sections")
        self.split_document.setChecked(bool(self.config["document"]["split_enabled"]))
        self.split_document.stateChanged.connect(self._split_changed)
        self.ocr_enabled = QCheckBox("Use local OCR for scanned pages and embedded images")
        self.ocr_enabled.setChecked(bool(self.config["document"]["ocr_enabled"]))
        self.ocr_enabled.stateChanged.connect(self._update_summary)
        self.context_budget_panel = QFrame()
        self.context_budget_panel.setObjectName("contextBudgetPanel")
        budget_layout = QVBoxLayout(self.context_budget_panel)
        budget_layout.setContentsMargins(0, 8, 0, 4)
        budget_label = QLabel("Context Budget")
        budget_label.setObjectName("fieldLabel")
        budget_note = QLabel(
            "Uses a model-independent estimated token count. Content is never intentionally "
            "removed to meet the budget."
        )
        budget_note.setObjectName("sectionDescription")
        budget_note.setWordWrap(True)
        self.context_budget = QComboBox()
        self.context_budget.addItem("No limit", None)
        self.context_budget.addItem("32K", 32000)
        self.context_budget.addItem("64K", 64000)
        self.context_budget.addItem("128K", 128000)
        self.context_budget.addItem("Custom", "custom")
        self.context_budget.currentIndexChanged.connect(self._budget_changed)
        self.custom_budget = QSpinBox()
        self.custom_budget.setRange(1000, 10000000)
        self.custom_budget.setSingleStep(1000)
        self.custom_budget.setSuffix(" estimated tokens")
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
        self.output_path.setPlaceholderText("Default: an AI素材处理结果 folder beside each source")
        self.output_path.textChanged.connect(self._update_summary)
        output_button = QPushButton("Choose…")
        output_button.setObjectName("secondary")
        output_button.clicked.connect(self._choose_output)
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output"))
        output_row.addWidget(self.output_path, 1)
        output_row.addWidget(output_button)
        basic.addLayout(output_row)
        layout.addWidget(self.basic_panel)

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setObjectName("documentAdvancedToggle")
        self.advanced_toggle.setText("Advanced options")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.toggled.connect(self._advanced_toggled)
        layout.addWidget(self.advanced_toggle)
        self.advanced_panel = QFrame()
        self.advanced_panel.setObjectName("documentAdvancedOptions")
        advanced = QVBoxLayout(self.advanced_panel)
        advanced.setContentsMargins(14, 10, 14, 12)
        target_label = QLabel("Target section length")
        target_label.setObjectName("fieldLabel")
        self.target_tokens = QSpinBox()
        self.target_tokens.setRange(500, 100000)
        self.target_tokens.setSingleStep(500)
        self.target_tokens.setSuffix(" estimated tokens / section")
        self.target_tokens.setValue(int(self.config["document"]["target_tokens"]))
        technical_note = QLabel(
            "Token values are estimates. Content is not silently removed to meet this length."
        )
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
        title = QLabel("Ready to prepare")
        title.setObjectName("sectionTitle")
        details = QHBoxLayout()
        self.summary_count = QLabel("Add documents to continue")
        self.summary_count.setObjectName("documentSummaryValue")
        self.summary_mode = QLabel("—")
        self.summary_mode.setObjectName("documentSummaryValue")
        self.summary_ocr = QLabel("OCR: —")
        self.summary_ocr.setObjectName("documentSummaryValue")
        self.summary_budget = QLabel()
        self.summary_budget.setObjectName("documentSummaryValue")
        self.summary_output = QLabel("Output: —")
        self.summary_output.setObjectName("documentSummaryValue")
        self.summary_output.setWordWrap(True)
        for widget in (
            self.summary_count,
            self.summary_mode,
            self.summary_ocr,
            self.summary_budget,
        ):
            details.addWidget(widget)
        details.addStretch()
        actions = QHBoxLayout()
        self.preview_button = QPushButton("预览文档处理方案")
        self.preview_button.setObjectName("secondary")
        self.preview_button.clicked.connect(self._show_preview)
        self.start_button = QPushButton("Prepare documents")
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
        self.technical_details_button = QPushButton("View technical details")
        self.technical_details_button.setObjectName("linkButton")
        self.technical_details_button.clicked.connect(self._show_technical_details)
        self.open_button = QPushButton("Open output")
        self.open_button.setObjectName("secondary")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(
            lambda: (
                self.open_output_requested.emit(self.last_outputs[0]) if self.last_outputs else None
            )
        )
        self.report_button = QPushButton("View Context Report")
        self.report_button.setObjectName("secondary")
        self.report_button.setVisible(False)
        self.report_button.clicked.connect(self._open_context_report)
        self.source_map_button = QPushButton("View Source Map")
        self.source_map_button.setObjectName("secondary")
        self.source_map_button.setVisible(False)
        self.source_map_button.clicked.connect(self._open_source_map)
        result_actions = QHBoxLayout()
        result_actions.addWidget(self.result_heading)
        result_actions.addStretch()
        result_actions.addWidget(self.technical_details_button)
        result_actions.addWidget(self.report_button)
        result_actions.addWidget(self.source_map_button)
        result_actions.addWidget(self.open_button)
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
        title = QLabel("Recent document tasks")
        title.setObjectName("sectionTitle")
        self.history_button = QPushButton("View document history")
        self.history_button.setObjectName("linkButton")
        self.history_button.clicked.connect(
            lambda: self.history_requested.emit(self.workspace_id.value)
        )
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.history_button)
        self.recent_tasks = QTableWidget(0, 4)
        self.recent_tasks.setHorizontalHeaderLabels(["Source", "Preparation", "Result", "Progress"])
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
            "Choose documents",
            "",
            "Documents (*.pdf *.doc *.docx *.ppt *.pptx *.xls *.xlsx *.html *.htm *.txt *.csv *.json *.xml *.md);;All files (*)",
        )
        self.add_inputs(paths)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a document folder")
        if path:
            self.add_inputs([path])

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose document output folder")
        if path:
            self.output_path.setText(path)

    def _render_input_paths(self) -> None:
        self.document_list.clear()
        for path in self.paths:
            try:
                size = _human_size(path.stat().st_size)
            except OSError:
                size = "Unavailable"
            item = QTreeWidgetItem(
                [path.name, path.suffix.upper().lstrip(".") or "FILE", size, str(path.parent)]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(0, str(path))
            item.setToolTip(3, str(path.parent))
            self.document_list.addTopLevelItem(item)
        count = len(self.paths)
        self.selected_count.setText(
            "No documents selected"
            if count == 0
            else f"{count} document{'s' if count != 1 else ''} selected"
        )
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
        self._operation_changed()

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
                "AI-ready Markdown"
                if self.document_mode.currentData() == "enhanced"
                else "Convert to Markdown"
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
            "" if ocr_available else "Local OCR is unavailable. Set it up in Documents Settings."
        )
        if markdown and enhanced:
            self.operation_description.setText(
                "Clean structure, run the existing quality checks, and optionally split long "
                "content while preserving source information."
            )
            self.output_hint.setText("Output: existing AI 资料包 format.")
        elif context_pack:
            self.operation_description.setText(
                "Combine one or more documents into traceable upload packs with a deterministic "
                "Context Budget and an integrity report."
            )
            self.output_hint.setText(
                "Output: START_HERE, complete content archive, numbered packs, source packages, "
                "manifest and Context Report."
            )
        elif markdown:
            self.operation_description.setText(
                "Keep the direct MarkItDown conversion without enhanced cleaning or splitting."
            )
            self.output_hint.setText("输出：单个 Markdown 文件。")
        elif operation is Operation.TO_PDF:
            self.operation_description.setText(
                "Create a PDF copy using Microsoft Office or LibreOffice. The source is unchanged."
            )
            self.output_hint.setText("输出：单个 PDF 文件。")
        else:
            self.operation_description.setText(
                "Select documents to see available preparation modes."
            )
            self.output_hint.setText("Add documents to see the output format.")
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
        self.summary_count.setText(
            "Add documents to continue"
            if count == 0
            else f"{count} document{'s' if count != 1 else ''}"
        )
        raw = self.operation.currentData()
        self.summary_mode.setText(
            self._operation_label(Operation(raw)) if raw is not None else "No compatible mode"
        )
        enhanced = (
            raw == Operation.TO_MARKDOWN.value and self.document_mode.currentData() == "enhanced"
        )
        ocr = enhanced and self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
        self.summary_ocr.setText("OCR: On" if ocr else "OCR: Off")
        context_pack = raw == Operation.DOCUMENT_CONTEXT_PACK.value
        self.summary_budget.setVisible(context_pack)
        if context_pack:
            budget = self._context_budget_value()
            self.summary_ocr.setText(
                "OCR: On"
                if self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
                else "OCR: Off"
            )
            self.summary_budget.setText(
                f"Context Budget: {budget:,} estimated tokens"
                if budget
                else "Context Budget: No limit"
            )
        if self.output_path.text().strip():
            output = self.output_path.text().strip()
        elif self.paths:
            output = str(self.output_for(self.paths[0]))
        else:
            output = "beside each source"
        self.summary_output.setText(f"Output: {output}")

    def _parameters(self) -> dict[str, object]:
        if self.operation.currentData() == Operation.DOCUMENT_CONTEXT_PACK.value:
            budget = self._context_budget_value()
            return {
                "Sources": len(self.paths),
                "Context Budget": f"{budget:,} estimated tokens" if budget else "No limit",
                "Estimated context": "Available after preprocessing",
                "OCR": "开启"
                if self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
                else "关闭",
                "Integrity": "No content will be intentionally removed",
            }
        enhanced = self.document_mode.currentData() == "enhanced"
        return {
            "模式": "AI 增强" if enhanced else "原始转换",
            "自动拆分": "是" if enhanced and self.split_document.isChecked() else "否",
            "目标长度": f"{self.target_tokens.value()} tokens",
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
            self.set_presentation_state(
                WorkspacePresentationState.ERROR, "Preview could not be created."
            )
            QMessageBox.critical(self, "Unable to preview", str(exc))

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
        self._reset_source_map()
        self.jobs_requested.emit(self.workspace_id.value, jobs)

    def set_presentation_state(
        self, state: WorkspacePresentationState, message: str | None = None
    ) -> None:
        self.presentation_state = state
        defaults = {
            WorkspacePresentationState.EMPTY: (
                "Add documents",
                "Waiting",
                "Choose files to begin.",
            ),
            WorkspacePresentationState.INPUTS_SELECTED: (
                "Ready to prepare",
                "Ready",
                f"{len(self.paths)} document{'s' if len(self.paths) != 1 else ''} selected.",
            ),
            WorkspacePresentationState.PREVIEW: (
                "Preview ready",
                "Not started",
                "Review the preview, then prepare your documents when ready.",
            ),
            WorkspacePresentationState.PROCESSING: (
                "Preparing documents",
                f"{self.workspace_progress.value()}%",
                "Switching workspaces will not cancel this task.",
            ),
            WorkspacePresentationState.SUCCESS: (
                "Documents ready",
                "Complete",
                "The original files were not changed.",
            ),
            WorkspacePresentationState.WARNING: (
                "Documents ready with warnings",
                "Check results",
                "Some items need attention. Completed outputs are available.",
            ),
            WorkspacePresentationState.ERROR: (
                "Preparation stopped",
                "Not completed",
                "The original files were not changed.",
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
            WorkspacePresentationState.EMPTY: DocumentMascotState.EMPTY,
            WorkspacePresentationState.INPUTS_SELECTED: DocumentMascotState.READY,
            WorkspacePresentationState.PREVIEW: DocumentMascotState.READY,
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
        self.state_heading.setText(f"Preparing documents · {value}%")

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
        overflow = int(context_report.get("overflow_packs", 0)) if context_report else 0
        self.report_button.setVisible(bool(context_report and outputs))
        self._source_map_pack_dir = Path(outputs[0]) if (context_report and outputs) else None
        self.source_map_button.setVisible(self._source_map_pack_dir is not None)
        state = (
            WorkspacePresentationState.WARNING
            if outputs and (errors or overflow)
            else WorkspacePresentationState.SUCCESS
            if outputs
            else WorkspacePresentationState.ERROR
        )
        if context_report:
            budget = context_report.get("requested_budget")
            pack_count = int(context_report.get("pack_count", 0))
            budget_label = f"{int(budget):,} estimated tokens" if budget else "No limit"
            self.result_heading.setText("Context Pack ready")
            self.result_details.setText(
                f"{context_report.get('source_count', 0)} sources · "
                f"{pack_count} pack{'s' if pack_count != 1 else ''} · "
                f"~{int(context_report.get('estimated_tokens', 0)):,} estimated tokens\n"
                f"Context Budget: {budget_label}"
            )
        else:
            self.result_heading.setText(
                f"{len(outputs)} output{'s' if len(outputs) != 1 else ''} created"
            )
            self.result_details.setText(
                "\n".join(outputs[:4]) + ("\n…" if len(outputs) > 4 else "")
            )
        self.set_presentation_state(
            state,
            f"Context Pack created with {overflow} over-budget pack. No content was removed."
            if overflow
            else f"{len(outputs)} completed; {len(errors)} need attention."
            if errors
            else f"{len(outputs)} completed. The original files were not changed.",
        )

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
            QMessageBox.critical(self, "Source Map unavailable", str(exc))
            return
        self.source_map_view.set_source_map(source_map)
        self.content_stack.setCurrentWidget(self.source_map_view)

    def _reset_source_map(self) -> None:
        self._source_map_pack_dir = None
        self.source_map_button.setVisible(False)
        self.source_map_view.set_source_map(None)
        self.content_stack.setCurrentIndex(0)

    def _close_source_map(self) -> None:
        self.content_stack.setCurrentIndex(0)

    def _show_technical_details(self) -> None:
        if self._technical_details:
            QMessageBox.information(self, "Technical details", self._technical_details)
