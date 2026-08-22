from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..models import TaskStatus

STATUS_LABELS = {
    TaskStatus.WAITING: "等待",
    TaskStatus.RUNNING: "运行中",
    TaskStatus.SUCCESS: "成功",
    TaskStatus.FAILED: "失败",
    TaskStatus.CANCELLED: "已取消",
    TaskStatus.INTERRUPTED: "已中断",
}


class TaskCenterPanel(QFrame):
    """Presentation-only task table with selection-aware action states."""

    selection_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("panel")
        self.rows: dict[str, int] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        header = QHBoxLayout()
        title = QLabel("任务中心")
        title.setObjectName("sectionTitle")
        self.cancel_button = QPushButton("取消所选任务")
        self.cancel_button.setObjectName("secondary")
        self.cancel_button.setEnabled(False)
        self.retry_button = QPushButton("重试失败任务")
        self.retry_button.setObjectName("secondary")
        self.retry_button.setEnabled(False)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.cancel_button)
        header.addWidget(self.retry_button)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["工作区", "文件", "操作", "状态", "进度", "详情"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(170)
        self.table.verticalHeader().setVisible(False)
        for column, mode in (
            (0, QHeaderView.ResizeMode.ResizeToContents),
            (1, QHeaderView.ResizeMode.Stretch),
            (2, QHeaderView.ResizeMode.ResizeToContents),
            (3, QHeaderView.ResizeMode.ResizeToContents),
            (4, QHeaderView.ResizeMode.ResizeToContents),
            (5, QHeaderView.ResizeMode.Stretch),
        ):
            self.table.horizontalHeader().setSectionResizeMode(column, mode)
        self.table.itemSelectionChanged.connect(self.selection_changed.emit)

        layout.addLayout(header)
        layout.addWidget(self.table)

    def upsert(
        self,
        task_id: str,
        workspace_label: str,
        source_name: str,
        operation_label: str,
        status: TaskStatus,
        progress: int,
        message: str,
    ) -> None:
        row = self.rows.get(task_id)
        if row is None:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(workspace_label))
            source_item = QTableWidgetItem(source_name)
            source_item.setData(Qt.ItemDataRole.UserRole, task_id)
            self.table.setItem(row, 1, source_item)
            self.table.setItem(row, 2, QTableWidgetItem(operation_label))
            self.rows[task_id] = row
        self.table.setItem(row, 3, QTableWidgetItem(STATUS_LABELS[status]))
        self.table.setItem(row, 4, QTableWidgetItem(f"{progress}%"))
        self.table.setItem(row, 5, QTableWidgetItem(message))
        self.table.item(row, 1).setData(Qt.ItemDataRole.UserRole + 1, status.value)

    def selected_task_ids(self) -> list[str]:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        return [
            str(self.table.item(row, 1).data(Qt.ItemDataRole.UserRole))
            for row in rows
            if self.table.item(row, 1) is not None
        ]

    def update_actions(
        self,
        *,
        running: bool,
        states: dict[str, TaskStatus],
    ) -> None:
        selected = self.selected_task_ids()
        self.cancel_button.setEnabled(
            bool(selected)
            and running
            and any(
                states.get(task_id) in {TaskStatus.WAITING, TaskStatus.RUNNING}
                for task_id in selected
            )
        )
        self.retry_button.setEnabled(
            bool(selected)
            and not running
            and any(
                states.get(task_id)
                in {
                    TaskStatus.WAITING,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                    TaskStatus.INTERRUPTED,
                }
                for task_id in selected
            )
        )
