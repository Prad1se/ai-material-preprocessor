from __future__ import annotations

import os
import sys
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QHideEvent, QImageReader, QMovie, QPixmap, QShowEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class DocumentMascotState(StrEnum):
    EMPTY = "empty"
    READY = "ready"
    PREVIEW = "preview"
    PROCESSING = "processing"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    COMPLETED = "completed"


DORO_STATE_ASSETS: dict[DocumentMascotState, str | None] = {
    DocumentMascotState.EMPTY: "orange.png",
    DocumentMascotState.READY: "ready.png",
    DocumentMascotState.PREVIEW: "carrying.jpg",
    DocumentMascotState.PROCESSING: "processing.gif",
    DocumentMascotState.SUCCESS: "cheering.webp",
    DocumentMascotState.WARNING: "wave.gif",
    DocumentMascotState.ERROR: None,
    DocumentMascotState.COMPLETED: "resting.gif",
}


_STATE_COPY = {
    DocumentMascotState.EMPTY: ("D", "Add documents to begin"),
    DocumentMascotState.READY: ("D", "Ready to prepare"),
    DocumentMascotState.PREVIEW: ("D", "Preview ready"),
    DocumentMascotState.PROCESSING: ("…", "Preparing documents"),
    DocumentMascotState.SUCCESS: ("✓", "Documents ready"),
    DocumentMascotState.WARNING: ("!", "Ready with warnings"),
    DocumentMascotState.ERROR: ("×", "Preparation stopped"),
    DocumentMascotState.COMPLETED: ("D", "Doro is resting"),
}


def doro_asset_path(filename: str) -> Path:
    """Resolve bundled Doro artwork, allowing an explicit local override."""
    override = os.environ.get("AI_MATERIAL_DORO_ASSET_DIR")
    if override:
        return Path(override) / filename
    if hasattr(sys, "_MEIPASS"):
        packaged = Path(sys._MEIPASS) / "assets" / "doro" / filename
        if packaged.is_file():
            return packaged
    executable_local = Path(sys.executable).resolve().parent / "assets" / "doro" / "local"
    if executable_local.is_dir():
        return executable_local / filename
    asset_root = Path(__file__).resolve().parents[3] / "assets" / "doro"
    canonical = asset_root / filename
    if canonical.is_file():
        return canonical
    return asset_root / "local" / filename


class DocumentMascotView(QWidget):
    """Accessible document status using bundled or user-overridden Doro artwork."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("documentMascot")
        self.setAccessibleName("Document workspace status")
        self.movie: QMovie | None = None
        self._active_asset_path: Path | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        self.artwork = QLabel()
        self.artwork.setObjectName("documentMascotArtwork")
        self.artwork.setFixedSize(140, 108)
        self.artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.symbol = QLabel()
        self.symbol.setObjectName("documentMascotSymbol")
        self.symbol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption = QLabel()
        self.caption.setObjectName("documentMascotCaption")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        layout.addWidget(self.artwork, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.symbol)
        layout.addWidget(self.caption)
        self.set_state(DocumentMascotState.EMPTY)

    def set_state(self, state: DocumentMascotState) -> None:
        symbol, caption = _STATE_COPY[state]
        self.state = state
        self.symbol.setText(symbol)
        self.caption.setText(caption)
        filename = DORO_STATE_ASSETS[state]
        self._set_artwork(doro_asset_path(filename) if filename else None)
        self.setProperty("mascotState", state.value)
        self.setAccessibleDescription(caption)
        self.style().unpolish(self)
        self.style().polish(self)

    def _set_artwork(self, path: Path | None) -> None:
        if path == self._active_asset_path and (
            self.movie is not None
            or (self.artwork.pixmap() is not None and not self.artwork.pixmap().isNull())
        ):
            return
        self._stop_movie()
        self.artwork.clear()
        self._active_asset_path = None
        if path is not None and path.suffix.casefold() == ".gif" and path.is_file():
            movie = QMovie(str(path), parent=self)
            if movie.isValid():
                source_size = QImageReader(str(path)).size()
                movie.setCacheMode(QMovie.CacheMode.CacheAll)
                movie.setScaledSize(
                    source_size.scaled(self.artwork.size(), Qt.AspectRatioMode.KeepAspectRatio)
                )
                self.movie = movie
                self._active_asset_path = path
                self.artwork.setMovie(movie)
                self.artwork.show()
                self.symbol.hide()
                movie.start()
                return
            movie.deleteLater()
        if path is not None and path.is_file():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.artwork.setPixmap(
                    pixmap.scaled(
                        self.artwork.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self._active_asset_path = path
                self.artwork.show()
                self.symbol.hide()
                return
        self.artwork.hide()
        self.symbol.show()

    def _stop_movie(self) -> None:
        if self.movie is None:
            return
        self.movie.stop()
        self.artwork.setMovie(None)
        self.movie.deleteLater()
        self.movie = None

    def hideEvent(self, event: QHideEvent) -> None:
        if self.movie is not None:
            self.movie.setPaused(True)
        super().hideEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self.movie is not None:
            self.movie.setPaused(False)
