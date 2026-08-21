from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class DocumentMascotState(StrEnum):
    EMPTY = "empty"
    READY = "ready"
    PROCESSING = "processing"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


_STATE_COPY = {
    DocumentMascotState.EMPTY: ("D", "Add documents to begin"),
    DocumentMascotState.READY: ("D", "Ready to prepare"),
    DocumentMascotState.PROCESSING: ("…", "Preparing documents"),
    DocumentMascotState.SUCCESS: ("✓", "Documents ready"),
    DocumentMascotState.WARNING: ("!", "Ready with warnings"),
    DocumentMascotState.ERROR: ("×", "Preparation stopped"),
}


class DocumentMascotView(QWidget):
    """Rights-safe presentation slot for future licensed Doro artwork."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("documentMascot")
        self.setAccessibleName("Document workspace status")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(3)
        self.symbol = QLabel()
        self.symbol.setObjectName("documentMascotSymbol")
        self.symbol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption = QLabel()
        self.caption.setObjectName("documentMascotCaption")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        layout.addWidget(self.symbol)
        layout.addWidget(self.caption)
        self.set_state(DocumentMascotState.EMPTY)

    def set_state(self, state: DocumentMascotState) -> None:
        symbol, caption = _STATE_COPY[state]
        self.state = state
        self.symbol.setText(symbol)
        self.caption.setText(caption)
        self.setProperty("mascotState", state.value)
        self.setAccessibleDescription(caption)
        self.style().unpolish(self)
        self.style().polish(self)
