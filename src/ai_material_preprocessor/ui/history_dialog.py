from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..application.workspaces import WorkspaceId, operations_for_workspace
from ..models import Operation, TaskStatus
from ..services.history_repository import HistoryEntry, HistoryRepository
from .theme import APP_STYLESHEET

STATUS_LABELS = {
    TaskStatus.WAITING: "等待",
    TaskStatus.RUNNING: "运行中",
    TaskStatus.SUCCESS: "成功",
    TaskStatus.FAILED: "失败",
    TaskStatus.CANCELLED: "已取消",
    TaskStatus.INTERRUPTED: "已中断",
}


class HistoryDetailsDialog(QDialog):
    def __init__(self, payload: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("任务详情与质量摘要")
        self.resize(760, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("详情来自应用数据目录中的处理记录，不包含文档正文。"))
        self.details = QPlainTextEdit(self._details_text(payload))
        self.details.setReadOnly(True)
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _details_text(payload: dict) -> str:
        sections = [
            f"任务编号：{payload.get('task_id', '—')}",
            f"执行时间：{payload.get('created_at', '—')}",
        ]
        for index, item in enumerate(payload.get("items") or [], start=1):
            sections.extend(
                [
                    "",
                    f"项目 {index}",
                    f"源文件：{item.get('source') or '—'}",
                    f"操作：{item.get('operation_label') or item.get('operation') or '—'}",
                    f"状态：{item.get('status') or '—'}",
                    f"输出：{item.get('output') or '—'}",
                ]
            )
            parameters = item.get("parameters") or {}
            if parameters:
                sections.append(
                    "参数：" + "；".join(f"{key}={value}" for key, value in parameters.items())
                )
            tools = item.get("tool_versions") or {}
            if tools:
                sections.append(
                    "工具：" + "；".join(f"{key} {value}" for key, value in tools.items())
                )
            quality = item.get("quality_summary") or {}
            if quality:
                sections.append(
                    f"质量：{quality.get('score', '—')}/100；"
                    f"约 {quality.get('estimated_tokens', '—')} tokens；"
                    f"拆分 {quality.get('chunk_count', 0)} 段"
                )
                for issue in quality.get("issues") or []:
                    sections.append(f"  • {issue.get('message') or issue.get('code')}")
        return "\n".join(sections)


class HistoryDialog(QDialog):
    """Searchable history UI; record and cache deletion stay separate."""

    def __init__(
        self,
        repository: HistoryRepository,
        parent: QWidget | None = None,
        *,
        workspace: WorkspaceId | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.setWindowTitle("处理历史")
        self.resize(980, 560)
        self.setStyleSheet(APP_STYLESHEET)

        root = QVBoxLayout(self)
        intro = QLabel("这里仅保存任务来源、参数和结果路径。删除记录不会删除原文件或正式输出。")
        intro.setWordWrap(True)
        root.addWidget(intro)

        filters = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索文件名、输出路径或任务编号")
        self.workspace_filter = QComboBox()
        self.workspace_filter.addItem("全部 Workspace", None)
        self.workspace_filter.addItem("Documents", WorkspaceId.DOCUMENTS.value)
        self.workspace_filter.addItem("Video", WorkspaceId.VIDEO.value)
        if workspace is not None:
            self.workspace_filter.setCurrentIndex(self.workspace_filter.findData(workspace.value))
        self.status_filter = QComboBox()
        self.status_filter.addItem("全部状态", None)
        for status, label in STATUS_LABELS.items():
            self.status_filter.addItem(label, status.value)
        self.operation_filter = QComboBox()
        self.operation_filter.addItem("全部操作", None)
        for operation in Operation:
            self.operation_filter.addItem(operation.value, operation.name)
        filters.addWidget(self.search_input, 2)
        filters.addWidget(self.workspace_filter, 1)
        filters.addWidget(self.status_filter, 1)
        filters.addWidget(self.operation_filter, 1)
        root.addLayout(filters)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["时间", "源文件", "操作", "状态", "输出", "任务编号"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table)

        actions = QHBoxLayout()
        self.open_folder_button = QPushButton("打开记录目录")
        self.details_button = QPushButton("查看详情")
        self.delete_records_button = QPushButton("删除所选记录")
        self.delete_records_button.setObjectName("dangerLinkButton")
        self.delete_caches_button = QPushButton("删除所选缓存")
        self.delete_caches_button.setObjectName("dangerLinkButton")
        self.clear_all_button = QPushButton("清空全部历史")
        self.clear_all_button.setObjectName("dangerLinkButton")
        actions.addWidget(self.open_folder_button)
        actions.addWidget(self.details_button)
        actions.addStretch()
        actions.addWidget(self.delete_caches_button)
        actions.addWidget(self.delete_records_button)
        actions.addWidget(self.clear_all_button)
        root.addLayout(actions)

        close_row = QHBoxLayout()
        close_row.addStretch()
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.reject)
        close_row.addWidget(self.close_button)
        root.addLayout(close_row)

        self.search_input.textChanged.connect(self.refresh)
        self.workspace_filter.currentIndexChanged.connect(self._workspace_changed)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.operation_filter.currentIndexChanged.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.open_folder_button.clicked.connect(self._open_folder)
        self.details_button.clicked.connect(self._show_details)
        self.table.itemDoubleClicked.connect(lambda _item: self._show_details())
        self.delete_records_button.clicked.connect(self._delete_selected_records)
        self.delete_caches_button.clicked.connect(self._delete_selected_caches)
        self.clear_all_button.clicked.connect(self._clear_all)
        self.refresh()

    def _workspace_changed(self) -> None:
        selected_operation = self.operation_filter.currentData()
        raw_workspace = self.workspace_filter.currentData()
        allowed = (
            operations_for_workspace(WorkspaceId(raw_workspace))
            if raw_workspace
            else frozenset(Operation)
        )
        self.operation_filter.blockSignals(True)
        self.operation_filter.clear()
        self.operation_filter.addItem("全部操作", None)
        for operation in Operation:
            if operation in allowed:
                self.operation_filter.addItem(operation.value, operation.name)
        restored = self.operation_filter.findData(selected_operation)
        self.operation_filter.setCurrentIndex(max(0, restored))
        self.operation_filter.blockSignals(False)
        self.refresh()

    @staticmethod
    def _joined_status(entry: HistoryEntry) -> str:
        return "、".join(STATUS_LABELS[status] for status in TaskStatus if status in entry.statuses)

    def refresh(self) -> None:
        raw_status = self.status_filter.currentData()
        raw_operation = self.operation_filter.currentData()
        entries = self.repository.search(
            query=self.search_input.text(),
            status=TaskStatus(raw_status) if raw_status else None,
            operation=Operation[raw_operation] if raw_operation else None,
        )
        raw_workspace = self.workspace_filter.currentData()
        if raw_workspace:
            allowed = operations_for_workspace(WorkspaceId(raw_workspace))
            entries = [entry for entry in entries if entry.operations & allowed]
        self.table.setRowCount(0)
        for entry in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            source_names = "、".join(path.name for path in entry.sources) or "—"
            operations = "、".join(
                operation.value for operation in Operation if operation in entry.operations
            )
            outputs = "、".join(str(path) for path in entry.outputs) or "—"
            values = [
                entry.created_at.astimezone().strftime("%Y-%m-%d %H:%M"),
                source_names,
                operations,
                self._joined_status(entry),
                outputs,
                entry.task_id,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, entry.task_id)
                    item.setData(Qt.ItemDataRole.UserRole + 1, bool(entry.cache_paths))
                self.table.setItem(row, column, item)
        self._update_actions()

    def _selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectedIndexes()})

    def _selected_task_ids(self) -> list[str]:
        return [
            str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
            for row in self._selected_rows()
        ]

    def _update_actions(self) -> None:
        rows = self._selected_rows()
        self.delete_records_button.setEnabled(bool(rows))
        self.details_button.setEnabled(len(rows) == 1)
        self.delete_caches_button.setEnabled(
            any(bool(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)) for row in rows)
        )
        self.clear_all_button.setEnabled(self.table.rowCount() > 0)

    def _open_folder(self) -> None:
        self.repository.root.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(self.repository.root))

    def _show_details(self) -> None:
        task_ids = self._selected_task_ids()
        if len(task_ids) != 1:
            return
        payload = self.repository.details(task_ids[0])
        if payload is None:
            QMessageBox.warning(self, "无法读取详情", "处理记录不存在或已经损坏。")
            return
        HistoryDetailsDialog(payload, self).exec()

    def _delete_selected_records(self) -> None:
        task_ids = self._selected_task_ids()
        if not task_ids:
            return
        answer = QMessageBox.question(
            self,
            "删除所选历史记录？",
            f"将永久删除 {len(task_ids)} 条记录。原文件、正式输出和缓存都不会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is QMessageBox.StandardButton.Yes:
            self.repository.delete_records(task_ids)
            self.refresh()

    def _delete_selected_caches(self) -> None:
        task_ids = self._selected_task_ids()
        if not task_ids:
            return
        answer = QMessageBox.question(
            self,
            "删除所选任务缓存？",
            "只会删除应用缓存目录中的预览和临时文件；历史记录、原文件和正式输出会保留。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is QMessageBox.StandardButton.Yes:
            self.repository.delete_caches(task_ids)
            self.refresh()

    def _clear_all(self) -> None:
        task_ids = [entry.task_id for entry in self.repository.all()]
        if not task_ids:
            return
        answer = QMessageBox.question(
            self,
            "清空全部历史？",
            f"将永久删除 {len(task_ids)} 条记录，但不删除缓存、原文件或正式输出。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is QMessageBox.StandardButton.Yes:
            self.repository.delete_records(task_ids)
            self.refresh()
