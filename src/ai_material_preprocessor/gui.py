from __future__ import annotations

import copy
import os
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .application.default_preview_registry import build_default_preview_registry
from .application.preview_registry import PreviewProviderRegistry
from .application.workspaces import WorkspaceId, workspace_for_operation
from .apps.documents.preview import DocumentPreviewPlan
from .apps.video.preview import VideoPreviewBatch
from .models import Job, TaskStatus, ToolStatus
from .services.config import load_config, save_config
from .services.environment import detect_tools
from .services.history_repository import HistoryRepository, default_cache_root
from .services.preview import completed_contact_sheet
from .services.source_map import load_source_map
from .services.task_manifest import resolve_history_root
from .services.task_repository import PersistentTaskQueue
from .services.tool_versions import detect_tools_with_versions
from .ui.about_dialog import AboutDialog
from .ui.handoff_dialog import CrossWorkspaceHandoffDialog
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
from .ui.welcome_dialog import WelcomeDialog
from .ui.workers import Worker
from .ui.workspaces.common import WorkspacePresentationState, WorkspaceView
from .ui.workspaces.documents import DocumentWorkspace
from .ui.workspaces.video import VideoWorkspace

ConfigSaver = Callable[[dict], object]
HandoffConfirmer = Callable[[WorkspaceId, WorkspaceId, list[Path]], bool]

__all__ = ["HistoryDialog", "MOUSE_STATE_ASSETS", "MainWindow", "mouse_asset_path"]


class MainWindow(QMainWindow):
    """Application shell for two independent workspaces and one shared runtime."""

    def __init__(
        self,
        *,
        config: dict | None = None,
        tools: dict[str, ToolStatus] | None = None,
        task_repository: PersistentTaskQueue | None = None,
        config_saver: ConfigSaver = save_config,
        handoff_confirmer: HandoffConfirmer | None = None,
        preview_registry: PreviewProviderRegistry | None = None,
    ) -> None:
        super().__init__()
        self.config = copy.deepcopy(config) if config is not None else load_config()
        self.config.setdefault("ui", {}).setdefault("last_workspace", WorkspaceId.DOCUMENTS.value)
        self.tools = tools or detect_tools(self.config)
        self.task_repository = task_repository
        self.config_saver = config_saver
        self.handoff_confirmer = handoff_confirmer or self._confirm_handoff
        self.preview_registry = preview_registry or build_default_preview_registry()
        self.worker: Worker | None = None
        self.last_worker: Worker | None = None
        self.active_job_workspace: WorkspaceId | None = None
        self.last_outputs: list[str] = []

        self.setWindowTitle("AI 素材预处理工具")
        self.resize(1280, 820)
        self.setMinimumSize(980, 700)
        self._build_ui()
        self._apply_style()
        self._show_workspace(self._configured_workspace(), persist=False)
        if self.task_repository is not None:
            self._restore_task_queue()

    @property
    def current_workspace(self) -> WorkspaceId:
        return self._current_workspace

    @property
    def current_workspace_view(self) -> WorkspaceView:
        return self.workspaces[self._current_workspace]

    def _configured_workspace(self) -> WorkspaceId:
        try:
            return WorkspaceId(str(self.config.get("ui", {}).get("last_workspace", "documents")))
        except ValueError:
            return WorkspaceId.DOCUMENTS

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("shell")
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        navigation = QFrame()
        navigation.setObjectName("workspaceNavigation")
        navigation.setFixedWidth(218)
        nav = QVBoxLayout(navigation)
        nav.setContentsMargins(20, 24, 20, 20)
        nav.setSpacing(9)
        brand = QLabel("AI 素材\n预处理工具")
        brand.setObjectName("shellBrand")
        nav.addWidget(brand)
        tagline = QLabel("两个工作区 · 一个本地核心")
        tagline.setObjectName("navHint")
        tagline.setWordWrap(True)
        nav.addWidget(tagline)
        nav.addSpacing(20)
        self.documents_nav = self._nav_button("▤  文档")
        self.video_nav = self._nav_button("▶  视频")
        self.tasks_nav = self._nav_button("☷  任务")
        self.workspace_group = QButtonGroup(self)
        self.workspace_group.setExclusive(True)
        for button in (self.documents_nav, self.video_nav, self.tasks_nav):
            self.workspace_group.addButton(button)
            nav.addWidget(button)
        nav.addStretch()
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("navSeparator")
        nav.addWidget(separator)
        self.history_button = self._nav_button("历史", checkable=False)
        self.settings_button = self._nav_button("设置", checkable=False)
        self.about_button = self._nav_button("关于", checkable=False)
        nav.addWidget(self.history_button)
        nav.addWidget(self.settings_button)
        nav.addWidget(self.about_button)
        shell.addWidget(navigation)

        self.workspace_stack = QStackedWidget()
        self.document_workspace = DocumentWorkspace(self.config, self.tools, self.preview_registry)
        self.video_workspace = VideoWorkspace(self.config, self.tools, self.preview_registry)
        self.workspaces: dict[WorkspaceId, WorkspaceView] = {
            WorkspaceId.DOCUMENTS: self.document_workspace,
            WorkspaceId.VIDEO: self.video_workspace,
        }
        self.document_index = self.workspace_stack.addWidget(self.document_workspace)
        self.video_index = self.workspace_stack.addWidget(self.video_workspace)
        self.tasks_page = self._build_tasks_page()
        self.tasks_index = self.workspace_stack.addWidget(self.tasks_page)
        shell.addWidget(self.workspace_stack, 1)
        self.setCentralWidget(central)

        self.documents_nav.clicked.connect(lambda: self.switch_workspace(WorkspaceId.DOCUMENTS))
        self.video_nav.clicked.connect(lambda: self.switch_workspace(WorkspaceId.VIDEO))
        self.tasks_nav.clicked.connect(self._show_tasks)
        self.history_button.clicked.connect(lambda: self._open_history(None))
        self.settings_button.clicked.connect(self._open_settings)
        self.about_button.clicked.connect(self._open_about)
        for workspace in self.workspaces.values():
            workspace.jobs_requested.connect(self._start_jobs)
            workspace.preview_ready.connect(self._present_preview)
            workspace.handoff_requested.connect(self._handoff_requested)
            workspace.history_requested.connect(lambda raw: self._open_history(WorkspaceId(raw)))
            workspace.open_output_requested.connect(self._open_output)
            workspace.settings_requested.connect(self._open_workspace_settings)

    @staticmethod
    def _nav_button(text: str, *, checkable: bool = True) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("workspaceNavButton")
        button.setCheckable(checkable)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _build_tasks_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("tasksPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 30, 34, 30)
        title = QLabel("共享任务中心")
        title.setObjectName("title")
        subtitle = QLabel("文档与视频任务共享同一运行环境；切换工作区不会取消任务。")
        subtitle.setObjectName("sectionDescription")
        self.task_panel = TaskCenterPanel()
        self.task_table = self.task_panel.table
        self.cancel_task_button = self.task_panel.cancel_button
        self.retry_task_button = self.task_panel.retry_button
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.status = QLabel("没有正在运行的任务")
        self.status.setObjectName("status")
        self.history_label = QLabel("任务与历史使用共享存储；所属工作区由处理类型判断。")
        self.history_label.setObjectName("historyLabel")
        self.history_label.setToolTip(str(resolve_history_root(self.config)))
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.task_panel, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(self.history_label)
        self.cancel_task_button.clicked.connect(self._cancel_selected_tasks)
        self.retry_task_button.clicked.connect(self._retry_selected_tasks)
        self.task_panel.selection_changed.connect(self._update_task_actions)
        return page

    def switch_workspace(self, workspace: WorkspaceId | str) -> None:
        self._show_workspace(WorkspaceId(workspace), persist=True)

    def _show_workspace(self, workspace: WorkspaceId, *, persist: bool) -> None:
        self._current_workspace = workspace
        self.workspace_stack.setCurrentIndex(
            self.document_index if workspace is WorkspaceId.DOCUMENTS else self.video_index
        )
        self.documents_nav.setChecked(workspace is WorkspaceId.DOCUMENTS)
        self.video_nav.setChecked(workspace is WorkspaceId.VIDEO)
        self.tasks_nav.setChecked(False)
        if persist:
            self.config.setdefault("ui", {})["last_workspace"] = workspace.value
            with suppress(OSError):
                self.config_saver(copy.deepcopy(self.config))

    def _show_tasks(self) -> None:
        self.workspace_stack.setCurrentIndex(self.tasks_index)
        self.documents_nav.setChecked(False)
        self.video_nav.setChecked(False)
        self.tasks_nav.setChecked(True)

    def _confirm_handoff(self, source: WorkspaceId, target: WorkspaceId, paths: list[Path]) -> bool:
        return CrossWorkspaceHandoffDialog.confirm(source, target, paths, self)

    def _handoff_requested(self, source: str, target: str, paths: list[Path]) -> None:
        source_id = WorkspaceId(source)
        target_id = WorkspaceId(target)
        if not self.handoff_confirmer(source_id, target_id, paths):
            return
        self.workspaces[target_id].accept_handoff(paths)
        self.switch_workspace(target_id)

    def _start_jobs(self, workspace: str, jobs: list[Job]) -> None:
        if self.worker is not None:
            QMessageBox.information(self, "已有任务运行中", "请等待当前批次结束或取消任务。")
            return
        if not jobs:
            return
        self.active_job_workspace = WorkspaceId(workspace)
        with suppress(OSError):
            self.config_saver(copy.deepcopy(self.config))
        origin = self.workspaces[self.active_job_workspace]
        origin.set_running(True)
        self.progress.setValue(0)
        self.status.setText("正在准备任务")
        self.worker = Worker(jobs, self.tools, self.config, task_repository=self.task_repository)
        for task in self.worker.tasks:
            if task.task_id in self.worker.tracked_ids:
                self._upsert_task(task.task_id, task.status, task.progress, task.message)
        self.worker.progress.connect(self._on_progress)
        self.worker.task_changed.connect(self._on_task_changed)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failure)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _restore_task_queue(self) -> None:
        recovery_worker = Worker([], self.tools, self.config, task_repository=self.task_repository)
        recoverable = [
            task
            for task in recovery_worker.tasks
            if task.status in {TaskStatus.WAITING, TaskStatus.INTERRUPTED}
        ]
        if not recoverable:
            return
        self.last_worker = recovery_worker
        for task in recoverable:
            self._upsert_task(task.task_id, task.status, task.progress, task.error or task.message)
        self.status.setText(f"发现 {len(recoverable)} 个上次未完成的任务；可选择后重试。")

    def _task_for(self, task_id: str):
        worker = self.worker or self.last_worker
        return (
            next((task for task in worker.tasks if task.task_id == task_id), None)
            if worker
            else None
        )

    def _upsert_task(self, task_id: str, status: TaskStatus, progress: int, message: str) -> None:
        task = self._task_for(task_id)
        if task is None:
            return
        self.task_panel.upsert(
            task_id,
            "文档"
            if workspace_for_operation(task.job.operation) is WorkspaceId.DOCUMENTS
            else "视频",
            task.job.source.name,
            task.job.operation.value,
            status,
            progress,
            message,
        )
        workspace = self.workspaces[workspace_for_operation(task.job.operation)]
        workspace.upsert_task(
            task_id, task.job.source.name, task.job.operation.value, status, progress
        )

    def _on_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.status.setText(message)
        if self.active_job_workspace is not None:
            self.workspaces[self.active_job_workspace].set_progress(value, message)

    def _on_task_changed(
        self, task_id: str, status_value: str, progress: int, message: str
    ) -> None:
        self._upsert_task(task_id, TaskStatus(status_value), progress, message)
        self._update_task_actions()

    def _update_task_actions(self) -> None:
        worker = self.worker or self.last_worker
        states = {task.task_id: task.status for task in worker.tasks} if worker else {}
        self.task_panel.update_actions(running=self.worker is not None, states=states)

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
        self.active_job_workspace = workspace_for_operation(retried[0].job.operation)
        self.worker = self.last_worker
        self.last_worker = None
        self.workspaces[self.active_job_workspace].set_running(True)
        self.worker.start()

    def _on_completed(
        self, outputs: list[str], errors: list[str], quality_reports: list[dict]
    ) -> None:
        self.last_outputs = outputs
        origin = (
            self.workspaces[self.active_job_workspace]
            if self.active_job_workspace is not None
            else self.current_workspace_view
        )
        origin.set_completed(outputs, errors, quality_reports)
        context_pack_reports = [
            report for report in quality_reports if report.get("context_pack_version") == 1
        ]
        document_reports = [
            report for report in quality_reports if report.get("context_pack_version") != 1
        ]
        if document_reports:
            DocumentReportDialog(document_reports, outputs, self).exec()
            if errors:
                QMessageBox.warning(self, "部分任务未完成", "\n".join(errors[:6]))
        elif context_pack_reports:
            source_map = None
            if outputs:
                try:
                    source_map = load_source_map(Path(outputs[0]))
                except (OSError, ValueError):
                    source_map = None
            DocumentReportDialog(context_pack_reports, outputs, self, source_map=source_map).exec()
            if errors:
                QMessageBox.warning(self, "AI 上下文包已完成，但需要检查", "\n".join(errors[:6]))
        elif errors:
            QMessageBox.warning(
                self,
                "部分任务未完成",
                "成功生成：" + str(len(outputs)) + "\n\n" + "\n".join(errors[:8]),
            )
        else:
            contact_sheet = next(
                (
                    path
                    for raw in outputs
                    if (path := completed_contact_sheet(Path(raw))) is not None
                ),
                None,
            )
            if contact_sheet is not None:
                source_name = origin.paths[0].name if origin.paths else contact_sheet.parent.name
                ContactSheetPreviewDialog(source_name, contact_sheet, self).exec()
            else:
                QMessageBox.information(
                    self,
                    "处理完成",
                    "已生成：\n" + "\n".join(outputs[:5]) + ("\n…" if len(outputs) > 5 else ""),
                )
        self.status.setText(
            f"处理结束：成功 {len(outputs)} 个，未完成 {len(errors)} 个；原文件未改动。"
        )

    def _worker_finished(self) -> None:
        self.last_worker = self.worker
        self.worker = None
        for workspace in self.workspaces.values():
            workspace.set_running(False)
        self._update_task_actions()

    def _on_failure(self, message: str) -> None:
        self.status.setText("处理失败；原文件未改动。")
        if self.active_job_workspace is not None:
            self.workspaces[self.active_job_workspace].set_presentation_state(
                WorkspacePresentationState.ERROR, message
            )
        QMessageBox.critical(self, "处理失败", message)

    def _present_preview(self, result: object) -> None:
        if isinstance(result, DocumentPreviewPlan):
            SourcePlanDialog(
                result.title, list(result.sources), result.parameters, result.note, self
            ).exec()
        elif isinstance(result, VideoPreviewBatch):
            VideoPreviewDialog(list(result.previews), self).exec()
        else:
            raise TypeError(f"Unsupported preview result: {type(result).__name__}")

    def _open_output(self, raw_output: str) -> None:
        output = Path(raw_output)
        folder = str(output if output.is_dir() else output.parent)
        if os.name == "nt":
            os.startfile(folder)

    def _open_history(self, workspace: WorkspaceId | None) -> None:
        repository = HistoryRepository(
            resolve_history_root(self.config), cache_root=default_cache_root()
        )
        HistoryDialog(repository, self, workspace=workspace).exec()

    def _open_settings(self) -> None:
        self._show_settings(None)

    def _open_workspace_settings(self, raw_workspace: str) -> None:
        self._show_settings(WorkspaceId(raw_workspace))

    def _show_settings(self, workspace: WorkspaceId | None) -> None:
        detected = detect_tools_with_versions(self.config)
        dialog = SettingsDialog(
            self.config,
            detected,
            self,
            initial_tab=workspace.value if workspace is not None else None,
        )
        dialog.settings_saved.connect(self._settings_applied)
        dialog.exec()

    def _settings_applied(self, config: dict, tools: dict[str, ToolStatus]) -> None:
        self.config = config
        self.config.setdefault("ui", {}).setdefault("last_workspace", self.current_workspace.value)
        self.tools = tools
        for workspace in self.workspaces.values():
            workspace.config = self.config
            workspace.set_tools(tools)
        self.history_label.setToolTip(str(resolve_history_root(self.config)))
        self._apply_style()

    def _open_about(self) -> None:
        AboutDialog(self.config, self).exec()

    def show_onboarding_if_needed(self) -> None:
        if bool(self.config["app"].get("onboarding_completed", False)):
            return
        self.welcome_dialog = WelcomeDialog(
            examples_dir=self._examples_dir(),
            theme=str(self.config["app"].get("theme", "system")),
            parent=self,
        )
        self.welcome_dialog.import_documents.connect(self._welcome_import_documents)
        self.welcome_dialog.view_example.connect(self._welcome_view_example)
        self.welcome_dialog.continue_setup.connect(self._show_onboarding)
        self.welcome_dialog.show()

    def _examples_dir(self) -> Path | None:
        candidate = Path(__file__).resolve().parents[2] / "examples"
        return candidate if candidate.is_dir() else None

    def _welcome_import_documents(self) -> None:
        self.switch_workspace(WorkspaceId.DOCUMENTS)
        self.document_workspace.add_button.click()

    def _welcome_view_example(self) -> None:
        examples = self._examples_dir()
        if examples is None:
            QMessageBox.information(self, "示例", "请从源代码仓库运行应用，以打开示例文件夹。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(examples)))

    def _show_onboarding(self) -> None:
        self.tools = detect_tools_with_versions(self.config)
        self.onboarding_dialog = OnboardingDialog(self.config, self.tools, self)
        self.onboarding_dialog.onboarding_completed.connect(self._settings_applied)
        self.onboarding_dialog.setModal(False)
        self.onboarding_dialog.show()

    def _apply_style(self) -> None:
        self.setStyleSheet(stylesheet_for_theme(self.config["app"].get("theme", "system")))


def launch_for_smoke_test() -> MainWindow:
    """Build a window without starting the event loop."""
    if QApplication.instance() is None:
        QApplication([])
    return MainWindow()
