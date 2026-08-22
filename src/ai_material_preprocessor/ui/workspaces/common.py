from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...application.preview_registry import PreviewProviderRegistry
from ...application.workspaces import WorkspaceId
from ...models import TaskStatus, ToolStatus


class WorkspacePresentationState(StrEnum):
    EMPTY = "empty"
    INPUTS_SELECTED = "inputs_selected"
    PREVIEW = "preview"
    PROCESSING = "processing"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class WorkspaceDropList(QListWidget):
    files_added = Signal(list)

    def __init__(self, description: str) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropZone")
        self.setAccessibleDescription(description)
        self.setMinimumHeight(190)

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


class WorkspaceView(QWidget):
    jobs_requested = Signal(str, object)
    preview_ready = Signal(object)
    handoff_requested = Signal(str, str, object)
    history_requested = Signal(str)
    open_output_requested = Signal(str)
    settings_requested = Signal(str)

    workspace_id: WorkspaceId
    input_title = "选择素材"
    input_description = ""
    input_accessible_description = ""

    def __init__(
        self,
        config: dict,
        tools: dict[str, ToolStatus],
        controller,
        preview_registry: PreviewProviderRegistry,
    ) -> None:
        super().__init__()
        self.config = config
        self.tools = tools
        self.controller = controller
        self.preview_registry = preview_registry
        self.paths: list[Path] = []
        self.last_outputs: list[str] = []
        self.presentation_state = WorkspacePresentationState.EMPTY
        self._task_rows: dict[str, int] = {}
        self.setObjectName(f"{self.workspace_id.value}Workspace")
        self._build_ui()
        self.refresh_operations()

    def _build_ui(self) -> None:
        page = QWidget()
        page.setObjectName("workspacePage")
        root = QVBoxLayout(page)
        root.setContentsMargins(28, 24, 32, 30)
        root.setSpacing(16)
        root.addWidget(self._create_hero())

        content = QHBoxLayout()
        content.setSpacing(16)
        input_panel = QFrame()
        input_panel.setObjectName("panel")
        input_layout = QVBoxLayout(input_panel)
        input_layout.setContentsMargins(22, 20, 22, 22)
        header = QHBoxLayout()
        title = QLabel(self.input_title)
        title.setObjectName("sectionTitle")
        self.add_button = QPushButton("选择文件…")
        self.add_button.setObjectName("secondary")
        self.folder_button = QPushButton("选择文件夹…")
        self.folder_button.setObjectName("secondary")
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("secondary")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.add_button)
        header.addWidget(self.folder_button)
        header.addWidget(self.clear_button)
        description = QLabel(self.input_description)
        description.setObjectName("sectionDescription")
        description.setWordWrap(True)
        self.file_list = WorkspaceDropList(self.input_accessible_description)
        input_layout.addLayout(header)
        input_layout.addWidget(description)
        input_layout.addWidget(self.file_list, 1)
        content.addWidget(input_panel, 5)
        content.addWidget(self._create_options_panel(), 4)
        root.addLayout(content)

        actions = QHBoxLayout()
        self.start_button = QPushButton("开始处理")
        self.start_button.setObjectName(
            "documentPrimary" if self.workspace_id is WorkspaceId.DOCUMENTS else "videoPrimary"
        )
        self.open_button = QPushButton("打开结果")
        self.open_button.setObjectName("secondary")
        self.open_button.setEnabled(False)
        self.history_button = QPushButton(
            "查看文档历史" if self.workspace_id is WorkspaceId.DOCUMENTS else "查看视频历史"
        )
        self.history_button.setObjectName("secondary")
        actions.addWidget(self.start_button, 2)
        actions.addWidget(self.open_button)
        actions.addWidget(self.history_button)
        root.addLayout(actions)

        recent = QFrame()
        recent.setObjectName("workspaceRecent")
        recent_layout = QVBoxLayout(recent)
        recent_title = QLabel(
            "Recent document tasks" if self.workspace_id is WorkspaceId.DOCUMENTS else "Media queue"
        )
        recent_title.setObjectName("sectionTitle")
        self.recent_tasks = QTableWidget(0, 4)
        self.recent_tasks.setHorizontalHeaderLabels(["文件", "操作", "状态", "进度"])
        self.recent_tasks.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.recent_tasks.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.recent_tasks.verticalHeader().setVisible(False)
        self.recent_tasks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.recent_tasks.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        recent_layout.addWidget(recent_title)
        recent_layout.addWidget(self.recent_tasks)
        root.addWidget(recent)

        self.workspace_progress = QProgressBar()
        self.workspace_progress.setValue(0)
        self.state_label = QLabel()
        self.state_label.setObjectName("status")
        root.addWidget(self.workspace_progress)
        root.addWidget(self.state_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self.add_button.clicked.connect(self._choose_files)
        self.folder_button.clicked.connect(self._choose_folder)
        self.clear_button.clicked.connect(self.clear_inputs)
        self.file_list.files_added.connect(self.add_inputs)
        self.start_button.clicked.connect(self._request_jobs)
        self.open_button.clicked.connect(
            lambda: (
                self.open_output_requested.emit(self.last_outputs[0]) if self.last_outputs else None
            )
        )
        self.history_button.clicked.connect(
            lambda: self.history_requested.emit(self.workspace_id.value)
        )
        self.set_presentation_state(WorkspacePresentationState.EMPTY)

    def _create_hero(self) -> QWidget:
        raise NotImplementedError

    def _create_options_panel(self) -> QWidget:
        raise NotImplementedError

    def _request_jobs(self) -> None:
        raise NotImplementedError

    def refresh_operations(self) -> None:
        raise NotImplementedError

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择素材文件")
        self.add_inputs(paths)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择素材文件夹")
        if path:
            self.add_inputs([path])

    def add_inputs(self, raw_paths: list[str]) -> None:
        selection = self.controller.classify_inputs(raw_paths)
        self._append_paths(selection.accepted)
        if selection.foreign and selection.foreign_workspace is not None:
            self.handoff_requested.emit(
                self.workspace_id.value,
                selection.foreign_workspace.value,
                list(selection.foreign),
            )

    def accept_handoff(self, paths: list[Path]) -> None:
        self._append_paths(tuple(paths))

    def _append_paths(self, paths: tuple[Path, ...]) -> None:
        known = {str(path).casefold() for path in self.paths}
        for path in paths:
            resolved = path.resolve()
            if str(resolved).casefold() in known:
                continue
            self.paths.append(resolved)
            known.add(str(resolved).casefold())
        self.paths.sort(key=lambda item: str(item).casefold())
        self._render_input_paths()
        self.refresh_operations()
        if self.paths:
            self.set_presentation_state(WorkspacePresentationState.INPUTS_SELECTED)

    def clear_inputs(self) -> None:
        self.paths.clear()
        self._render_input_paths()
        self.refresh_operations()
        self.set_presentation_state(WorkspacePresentationState.EMPTY)

    def _render_input_paths(self) -> None:
        self.file_list.clear()
        self.file_list.addItems([str(path) for path in self.paths])

    def output_for(self, source: Path) -> Path:
        explicit = self.output_path.text().strip()
        return (
            Path(explicit).resolve()
            if explicit
            else source.parent / str(self.config["output_folder_name"])
        )

    def set_tools(self, tools: dict[str, ToolStatus]) -> None:
        self.tools = tools
        self.controller.update_tools(tools)
        self.refresh_operations()

    def set_running(self, running: bool) -> None:
        if running:
            self.start_button.setEnabled(False)
            self.set_presentation_state(WorkspacePresentationState.PROCESSING)
        else:
            self.refresh_operations()

    def set_presentation_state(
        self,
        state: WorkspacePresentationState,
        message: str | None = None,
    ) -> None:
        self.presentation_state = state
        defaults = {
            WorkspacePresentationState.EMPTY: "等待素材",
            WorkspacePresentationState.INPUTS_SELECTED: f"已选择 {len(self.paths)} 个素材",
            WorkspacePresentationState.PREVIEW: "已生成处理预览，尚未开始任务",
            WorkspacePresentationState.PROCESSING: "正在处理，切换 Workspace 不会取消任务",
            WorkspacePresentationState.SUCCESS: "处理完成，原文件未改动",
            WorkspacePresentationState.WARNING: "处理完成，但有需要检查的项目",
            WorkspacePresentationState.ERROR: "处理未完成，原文件未改动",
        }
        self.state_label.setText(message or defaults[state])
        self.setProperty("presentationState", state.value)

    def set_progress(self, value: int, message: str) -> None:
        self.workspace_progress.setValue(value)
        self.set_presentation_state(WorkspacePresentationState.PROCESSING, message)

    def set_completed(
        self,
        outputs: list[str],
        errors: list[str],
        quality_reports: list[dict] | None = None,
    ) -> None:
        del quality_reports
        self.last_outputs = outputs
        self.open_button.setEnabled(bool(outputs))
        self.workspace_progress.setValue(
            100 if outputs and not errors else self.workspace_progress.value()
        )
        self.set_presentation_state(
            WorkspacePresentationState.WARNING
            if outputs and errors
            else WorkspacePresentationState.SUCCESS
            if outputs
            else WorkspacePresentationState.ERROR,
            f"已生成 {len(outputs)} 项" if outputs else "没有生成输出",
        )

    def upsert_task(
        self,
        task_id: str,
        filename: str,
        operation: str,
        status: TaskStatus,
        progress: int,
    ) -> None:
        row = self._task_rows.get(task_id)
        if row is None:
            row = self.recent_tasks.rowCount()
            self.recent_tasks.insertRow(row)
            self._task_rows[task_id] = row
        for column, value in enumerate((filename, operation, status.value, f"{progress}%")):
            self.recent_tasks.setItem(row, column, QTableWidgetItem(value))
