from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ..services.tool_capabilities import ToolCapability
from ..services.tool_installer import DEFAULT_TOOL_SPECS


class ToolStatusTable(QTableWidget):
    install_requested = Signal(str)

    _COMPACT_VIEWPORT_WIDTH = 720
    _COMPACT_CAPABILITY_WIDTH = 170
    # The application stylesheet is applied after the table is populated and adds
    # horizontal button padding, so reserve its themed width up front.
    _MIN_ACTION_WIDTH = 188

    def __init__(self) -> None:
        super().__init__(0, 6)
        self._action_buttons: dict[str, QPushButton] = {}
        self._action_column_width = self._MIN_ACTION_WIDTH
        self.setHorizontalHeaderLabels(["能力", "状态", "版本", "来源", "位置", "补充"])
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setMinimumSectionSize(48)
        header.setStretchLastSection(False)
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
                detail = (
                    capability.status.detail
                    or capability.installation_hint
                    or capability.status.path
                )
                item.setToolTip(value if not detail else f"{value}\n{detail}")
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
        self._action_column_width = max(
            [self._MIN_ACTION_WIDTH]
            + [button.sizeHint().width() + 8 for button in self._action_buttons.values()]
        )
        self._apply_column_layout()

    def action_button(self, key: str) -> QPushButton | None:
        return self._action_buttons.get(key)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_column_layout()

    def _apply_column_layout(self) -> None:
        compact = self.viewport().width() < self._COMPACT_VIEWPORT_WIDTH
        header = self.horizontalHeader()
        self.setColumnHidden(2, compact)
        self.setColumnHidden(3, compact)
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Fixed if compact else QHeaderView.ResizeMode.ResizeToContents,
        )
        if compact:
            self.setColumnWidth(0, self._COMPACT_CAPABILITY_WIDTH)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(5, self._action_column_width)
        self.horizontalScrollBar().setValue(0)
