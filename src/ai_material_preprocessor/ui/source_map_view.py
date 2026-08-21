from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..services.source_map import SourceMap, SourceMapEntry, SourceMapSource
from ..services.source_open import (
    SourceOpenCapability,
    SourceOpenTarget,
    resolve_source_open_target,
)

EMPTY_MESSAGE = "No Source Map available"
DEGRADED_CONTENT = "(processed content unavailable; manifest-only record)"


class SourceMapView(QWidget):
    back_requested = Signal()
    open_source_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sourceMapPage")
        self._entries: list[SourceMapEntry] = []
        self._sources: dict[str, SourceMapSource] = {}
        self._source_paths: dict[str, Path] = {}
        self._active_target: SourceOpenTarget | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 34, 32)
        root.setSpacing(16)
        root.addWidget(self._create_header())
        self._stack = QStackedWidget()
        self._empty_page = self._create_empty_state()
        self._body_page = self._create_body()
        self._stack.addWidget(self._empty_page)
        self._stack.addWidget(self._body_page)
        root.addWidget(self._stack, 1)
        self._stack.setCurrentWidget(self._empty_page)

    def _create_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.back_button = QPushButton("← Back to documents")
        self.back_button.setObjectName("linkButton")
        self.back_button.clicked.connect(lambda: self.back_requested.emit())
        copy = QVBoxLayout()
        title = QLabel("Source Map")
        title.setObjectName("title")
        subtitle = QLabel("Trace each Context Pack block back to its original document location.")
        subtitle.setObjectName("subtitle")
        copy.addWidget(title)
        copy.addWidget(subtitle)
        layout.addWidget(self.back_button)
        layout.addLayout(copy, 1)
        return header

    def _create_empty_state(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.empty_label = QLabel(EMPTY_MESSAGE)
        self.empty_label.setObjectName("sectionTitle")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint = QLabel(
            "Generate an AI Context Pack first; the Source Map appears after processing."
        )
        self.empty_hint.setObjectName("sectionDescription")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setWordWrap(True)
        layout.addStretch()
        layout.addWidget(self.empty_label)
        layout.addWidget(self.empty_hint)
        layout.addStretch()
        return page

    def _create_body(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._create_blocks_pane(), 3)
        layout.addWidget(self._create_content_pane(), 4)
        layout.addWidget(self._create_source_card(), 3)
        return page

    def _create_blocks_pane(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        header = QHBoxLayout()
        title = QLabel("Blocks")
        title.setObjectName("sectionTitle")
        self.block_count = QLabel()
        self.block_count.setObjectName("fieldLabel")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.block_count)
        self.blocks_table = QTableWidget(0, 4)
        self.blocks_table.setObjectName("sourceMapBlocks")
        self.blocks_table.setHorizontalHeaderLabels(["Block", "Source", "Section", "Order"])
        self.blocks_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.blocks_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.blocks_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.blocks_table.verticalHeader().setVisible(False)
        self.blocks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.blocks_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.blocks_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.blocks_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.blocks_table.setMinimumWidth(280)
        self.blocks_table.currentCellChanged.connect(self._on_current_cell_changed)
        self.blocks_table.setAccessibleName("Source Map blocks")
        self.integrity_notice = QLabel(
            "Integrity check incomplete. Some block content may be unavailable or inconsistent."
        )
        self.integrity_notice.setObjectName("sectionDescription")
        self.integrity_notice.setWordWrap(True)
        self.integrity_notice.setVisible(False)
        layout.addLayout(header)
        layout.addWidget(self.integrity_notice)
        layout.addWidget(self.blocks_table, 1)
        return panel

    def _create_content_pane(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        title = QLabel("Processed content")
        title.setObjectName("sectionTitle")
        meta = QHBoxLayout()
        self.heading_label = QLabel()
        self.heading_label.setObjectName("fieldLabel")
        self.token_label = QLabel()
        self.token_label.setObjectName("fieldLabel")
        meta.addWidget(self.heading_label, 1)
        meta.addWidget(self.token_label)
        self.content_edit = QPlainTextEdit()
        self.content_edit.setReadOnly(True)
        self.content_edit.setPlaceholderText("Select a block to view its processed content.")
        self.content_edit.setAccessibleName("Processed content")
        layout.addWidget(title)
        layout.addLayout(meta)
        layout.addWidget(self.content_edit, 1)
        return panel

    def _create_source_card(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        title = QLabel("Source")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.card_file_value = self._card_row(layout, "File")
        self.card_format_value = self._card_row(layout, "Format")
        self.card_source_id_value = self._card_row(layout, "Source ID")
        self.card_location_value = self._card_row(layout, "Location")
        self.card_capability_value = self._card_row(layout, "Open capability")
        self.card_fallback_note = QLabel(
            "Document-level fallback: no reliable page, slide, or sheet location."
        )
        self.card_fallback_note.setObjectName("sectionDescription")
        self.card_fallback_note.setWordWrap(True)
        self.card_fallback_note.setVisible(False)
        layout.addWidget(self.card_fallback_note)
        self.open_source_note = QLabel()
        self.open_source_note.setObjectName("sectionDescription")
        self.open_source_note.setWordWrap(True)
        self.open_source_button = QPushButton("Open source location")
        self.open_source_button.setObjectName("secondary")
        self.open_source_button.setEnabled(False)
        self.open_source_button.clicked.connect(self._request_source_open)
        layout.addWidget(self.open_source_note)
        layout.addWidget(self.open_source_button)
        layout.addStretch()
        return panel

    def _card_row(self, parent: QVBoxLayout, field: str) -> QLabel:
        label = QLabel(field)
        label.setObjectName("fieldLabel")
        value = QLabel()
        value.setObjectName("documentSummaryValue")
        value.setWordWrap(True)
        parent.addWidget(label)
        parent.addWidget(value)
        parent.addSpacing(6)
        return value

    def _on_current_cell_changed(
        self,
        current_row: int,
        _current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        self._render_entry(current_row)

    def set_source_map(
        self, source_map: SourceMap | None, source_paths: dict[str, Path] | None = None
    ) -> None:
        self.blocks_table.setRowCount(0)
        self.block_count.clear()
        self.heading_label.clear()
        self.token_label.clear()
        self.content_edit.clear()
        self.card_file_value.clear()
        self.card_format_value.clear()
        self.card_source_id_value.clear()
        self.card_location_value.clear()
        self.card_capability_value.clear()
        self.open_source_note.clear()
        self.open_source_button.setEnabled(False)
        self._active_target = None
        self.card_fallback_note.setVisible(False)
        self.integrity_notice.setVisible(bool(source_map and source_map.degraded))
        self._entries = list(source_map.entries) if source_map is not None else []
        self._sources = (
            {source.source_id: source for source in source_map.sources}
            if source_map is not None
            else {}
        )
        self._source_paths = dict(source_paths or {})
        if not self._entries:
            self._stack.setCurrentWidget(self._empty_page)
            return
        for entry in self._entries:
            source = self._sources.get(entry.source_id)
            source_name = source.display_name if source is not None else entry.source_id
            heading = " > ".join(entry.heading_context)
            row = self.blocks_table.rowCount()
            self.blocks_table.insertRow(row)
            values = [entry.block_id, source_name, heading, str(entry.block_order)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.blocks_table.setItem(row, column, item)
        self.block_count.setText(f"{len(self._entries)} blocks")
        self._stack.setCurrentWidget(self._body_page)
        self.blocks_table.setCurrentCell(0, 0)

    def _render_entry(self, row: int) -> None:
        if not (0 <= row < len(self._entries)):
            return
        entry = self._entries[row]
        source = self._sources.get(entry.source_id)
        self.heading_label.setText(" > ".join(entry.heading_context) or "—")
        self.token_label.setText(f"~{entry.estimated_tokens:,} tokens")
        self.content_edit.setPlainText(entry.content or DEGRADED_CONTENT)
        self.card_file_value.setText(source.display_name if source is not None else entry.source_id)
        self.card_format_value.setText(source.source_format if source is not None else "")
        self.card_source_id_value.setText(entry.source_id)
        self.card_location_value.setText(entry.effective_display)
        fallback = entry.primary_location is None or entry.primary_location.fallback
        self.card_fallback_note.setVisible(fallback)
        if source is None:
            self.card_capability_value.setText("Unavailable")
            self.open_source_note.setText("Source metadata is unavailable.")
            self.open_source_button.setEnabled(False)
            self._active_target = None
            return
        target = resolve_source_open_target(source, entry, self._source_paths.get(source.source_id))
        self._active_target = target
        labels = {
            SourceOpenCapability.PAGE_LEVEL: "Page-level (viewer permitting)",
            SourceOpenCapability.DOCUMENT_LEVEL: "Document-level",
            SourceOpenCapability.UNAVAILABLE: "Unavailable",
        }
        self.card_capability_value.setText(labels[target.capability])
        self.open_source_note.setText(target.reason)
        self.open_source_button.setEnabled(target.available)

    def _request_source_open(self) -> None:
        if self._active_target is not None and self._active_target.available:
            self.open_source_requested.emit(self._active_target)
