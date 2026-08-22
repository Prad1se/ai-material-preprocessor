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
    QSplitter,
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

EMPTY_MESSAGE = "暂无来源映射"
DEGRADED_CONTENT = "（已处理内容不可用；仅有清单记录）"


def _location_display(location: object | None) -> str:
    """Localize persisted provenance labels without changing the schema."""
    if location is None:
        return "文档级定位"
    kind = str(getattr(location, "kind", "document"))
    ordinal = getattr(location, "ordinal", None)
    label = str(getattr(location, "label", "") or "")
    confidence = getattr(location, "confidence", None)
    if kind == "page" and ordinal is not None:
        return f"第 {ordinal} 页"
    if kind == "slide" and ordinal is not None:
        return f"第 {ordinal} 张幻灯片"
    if kind == "worksheet" and label:
        return f"工作表：{label}"
    if kind == "ocr":
        value = f"OCR：{label}" if label else "OCR"
        if confidence is not None:
            value += f"（置信度 {confidence:.0%}）"
        return value
    return "文档级定位"


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
        self.back_button = QPushButton("← 返回文档")
        self.back_button.setObjectName("linkButton")
        self.back_button.clicked.connect(lambda: self.back_requested.emit())
        copy = QVBoxLayout()
        title = QLabel("来源映射")
        title.setObjectName("title")
        subtitle = QLabel("追踪上下文包中每个内容块对应的原始文档位置。")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
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
        self.empty_hint = QLabel("请先生成 AI 上下文包；处理完成后会显示来源映射。")
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
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(True)
        splitter.setHandleWidth(8)
        splitter.addWidget(self._create_blocks_pane())
        splitter.addWidget(self._create_content_pane())
        splitter.addWidget(self._create_source_card())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 3)
        layout.addWidget(splitter)
        return page

    def _create_blocks_pane(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        header = QHBoxLayout()
        title = QLabel("内容块")
        title.setObjectName("sectionTitle")
        self.block_count = QLabel()
        self.block_count.setObjectName("fieldLabel")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.block_count)
        self.blocks_table = QTableWidget(0, 4)
        self.blocks_table.setObjectName("sourceMapBlocks")
        self.blocks_table.setHorizontalHeaderLabels(["内容块", "来源", "章节", "顺序"])
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
        self.blocks_table.setMinimumWidth(0)
        self.blocks_table.currentCellChanged.connect(self._on_current_cell_changed)
        self.blocks_table.setAccessibleName("来源映射内容块")
        self.integrity_notice = QLabel("完整性检查未完成，部分内容块可能不可用或不一致。")
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
        title = QLabel("已处理内容")
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
        self.content_edit.setPlaceholderText("选择内容块后查看已处理内容。")
        self.content_edit.setAccessibleName("已处理内容")
        layout.addWidget(title)
        layout.addLayout(meta)
        layout.addWidget(self.content_edit, 1)
        return panel

    def _create_source_card(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        title = QLabel("来源")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.card_file_value = self._card_row(layout, "文件")
        self.card_format_value = self._card_row(layout, "格式")
        self.card_source_id_value = self._card_row(layout, "来源 ID")
        self.card_location_value = self._card_row(layout, "位置")
        self.card_capability_value = self._card_row(layout, "定位能力")
        self.card_fallback_note = QLabel("文档级回退：没有可靠的页码、幻灯片或工作表位置。")
        self.card_fallback_note.setObjectName("sectionDescription")
        self.card_fallback_note.setWordWrap(True)
        self.card_fallback_note.setVisible(False)
        layout.addWidget(self.card_fallback_note)
        self.open_source_note = QLabel()
        self.open_source_note.setObjectName("sectionDescription")
        self.open_source_note.setWordWrap(True)
        self.open_source_button = QPushButton("打开来源位置")
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
        self.block_count.setText(f"{len(self._entries)} 个内容块")
        self._stack.setCurrentWidget(self._body_page)
        self.blocks_table.setCurrentCell(0, 0)

    def _render_entry(self, row: int) -> None:
        if not (0 <= row < len(self._entries)):
            return
        entry = self._entries[row]
        source = self._sources.get(entry.source_id)
        self.heading_label.setText(" > ".join(entry.heading_context) or "—")
        self.token_label.setText(f"约 {entry.estimated_tokens:,} 个估算令牌")
        self.content_edit.setPlainText(entry.content or DEGRADED_CONTENT)
        self.card_file_value.setText(source.display_name if source is not None else entry.source_id)
        self.card_format_value.setText(source.source_format if source is not None else "")
        self.card_source_id_value.setText(entry.source_id)
        self.card_location_value.setText(_location_display(entry.primary_location))
        fallback = entry.primary_location is None or entry.primary_location.fallback
        self.card_fallback_note.setVisible(fallback)
        if source is None:
            self.card_capability_value.setText("不可用")
            self.open_source_note.setText("来源元数据不可用。")
            self.open_source_button.setEnabled(False)
            self._active_target = None
            return
        target = resolve_source_open_target(source, entry, self._source_paths.get(source.source_id))
        self._active_target = target
        labels = {
            SourceOpenCapability.PAGE_LEVEL: "页级定位（取决于查看器）",
            SourceOpenCapability.DOCUMENT_LEVEL: "文档级定位",
            SourceOpenCapability.UNAVAILABLE: "不可用",
        }
        self.card_capability_value.setText(labels[target.capability])
        self.open_source_note.setText(target.reason)
        self.open_source_button.setEnabled(target.available)

    def _request_source_open(self) -> None:
        if self._active_target is not None and self._active_target.available:
            self.open_source_requested.emit(self._active_target)
