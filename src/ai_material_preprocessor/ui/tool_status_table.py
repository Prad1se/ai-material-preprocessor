from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QTableWidget, QTableWidgetItem

from ..services.tool_capabilities import ToolCapability


class ToolStatusTable(QTableWidget):
    def __init__(self) -> None:
        super().__init__(0, 5)
        self.setHorizontalHeaderLabels(["能力", "状态", "版本", "来源", "位置"])
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.setMinimumHeight(260)

    def set_capabilities(self, capabilities: tuple[ToolCapability, ...]) -> None:
        self.setRowCount(len(capabilities))
        for row, capability in enumerate(capabilities):
            values = (
                capability.display_name,
                capability.status_text,
                capability.status.version or "—",
                capability.status.source or "—",
                capability.status.path or "—",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    capability.status.detail
                    or capability.installation_hint
                    or capability.status.path
                    or ""
                )
                if column == 1:
                    item.setData(Qt.ItemDataRole.UserRole, capability.state.value)
                self.setItem(row, column, item)
        self.resizeColumnsToContents()
        self.setColumnWidth(4, max(260, self.columnWidth(4)))
