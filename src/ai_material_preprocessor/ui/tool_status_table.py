from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QPushButton, QTableWidget, QTableWidgetItem

from ..services.tool_capabilities import ToolCapability
from ..services.tool_installer import DEFAULT_TOOL_SPECS


class ToolStatusTable(QTableWidget):
    install_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__(0, 6)
        self._action_buttons: dict[str, QPushButton] = {}
        self.setHorizontalHeaderLabels(["能力", "状态", "版本", "来源", "位置", "补充"])
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.setMinimumHeight(260)

    def set_capabilities(self, capabilities: tuple[ToolCapability, ...]) -> None:
        self._action_buttons.clear()
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
            spec_key = "ffmpeg" if capability.key == "ffprobe" else capability.key
            spec = DEFAULT_TOOL_SPECS.get(spec_key)
            if not capability.status.available and spec is not None:
                button = QPushButton(spec.action_label)
                button.setObjectName("secondary")
                button.setToolTip(
                    f"{spec.description}\n来源：{spec.source_url}\n许可证：{spec.license_name}"
                )
                button.clicked.connect(
                    lambda _checked=False, requested=spec_key: self.install_requested.emit(
                        requested
                    )
                )
                self.setCellWidget(row, 5, button)
                self._action_buttons[capability.key] = button
            else:
                self.setItem(row, 5, QTableWidgetItem("—"))
        self.resizeColumnsToContents()
        self.setColumnWidth(4, max(260, self.columnWidth(4)))

    def action_button(self, key: str) -> QPushButton | None:
        return self._action_buttons.get(key)
