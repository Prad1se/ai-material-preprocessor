from __future__ import annotations

import os
import sys
from collections import deque
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QHideEvent, QImage, QImageReader, QMovie, QPixmap, QShowEvent
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
    DocumentMascotState.EMPTY: ("D", "请导入文档"),
    DocumentMascotState.READY: ("D", "资料已准备"),
    DocumentMascotState.PREVIEW: ("D", "预览已准备"),
    DocumentMascotState.PROCESSING: ("…", "正在处理文档"),
    DocumentMascotState.SUCCESS: ("✓", "文档已准备好"),
    DocumentMascotState.WARNING: ("!", "已完成，但有提醒"),
    DocumentMascotState.ERROR: ("×", "处理已停止"),
    DocumentMascotState.COMPLETED: ("D", "Doro 正在休息"),
}


def _background_kind(red: int, green: int, blue: int) -> str | None:
    """Return a removable edge-background family without touching character fills."""
    if max(red, green, blue) - min(red, green, blue) <= 22 and min(red, green, blue) >= 232:
        return "light"
    if green >= 170 and green > red * 1.28 and green > blue * 1.18:
        return "green"
    return None


def transparentize_edge_background(image: QImage) -> QImage:
    """Remove only edge-connected near-white or green background pixels.

    The original Doro assets remain untouched on disk. Flood-filling from the image
    border means white areas enclosed by the character outline (for example the
    body) are preserved. This is also applied frame-by-frame to animated assets.
    """
    result = image.convertToFormat(QImage.Format.Format_ARGB32)
    width, height = result.width(), result.height()
    if width <= 0 or height <= 0:
        return result
    visited: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        for y in (0, height - 1):
            color = result.pixelColor(x, y)
            if _background_kind(color.red(), color.green(), color.blue()) is not None:
                queue.append((x, y))
    for y in range(height):
        for x in (0, width - 1):
            color = result.pixelColor(x, y)
            if _background_kind(color.red(), color.green(), color.blue()) is not None:
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        if (x, y) in visited:
            continue
        color = result.pixelColor(x, y)
        if _background_kind(color.red(), color.green(), color.blue()) is None:
            continue
        visited.add((x, y))
        color.setAlpha(0)
        result.setPixelColor(x, y, color)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                queue.append((nx, ny))
    return result


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
        self.setAccessibleName("文档工作区状态")
        self.movie: QMovie | None = None
        self._movie_frame_cache: dict[int, QPixmap] = {}
        self._active_asset_path: Path | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        self.artwork = QLabel()
        self.artwork.setObjectName("documentMascotArtwork")
        self.artwork.setFixedSize(140, 108)
        self.artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
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
        self._movie_frame_cache.clear()
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
                movie.frameChanged.connect(self._render_movie_frame)
                self.artwork.show()
                self.symbol.hide()
                movie.start()
                self._render_movie_frame()
                return
            movie.deleteLater()
        if path is not None and path.is_file():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.artwork.setPixmap(
                    QPixmap.fromImage(transparentize_edge_background(pixmap.toImage())).scaled(
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

    def _render_movie_frame(self, _frame: int | None = None) -> None:
        if self.movie is None:
            return
        frame_number = self.movie.currentFrameNumber() if _frame is None else _frame
        if frame_number in self._movie_frame_cache:
            self.artwork.setPixmap(self._movie_frame_cache[frame_number])
            self.artwork.show()
            self.symbol.hide()
            return
        image = self.movie.currentImage()
        if image.isNull():
            return
        pixmap = QPixmap.fromImage(transparentize_edge_background(image)).scaled(
            self.artwork.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._movie_frame_cache[frame_number] = pixmap
        self.artwork.setPixmap(pixmap)
        self.artwork.show()
        self.symbol.hide()

    def _stop_movie(self) -> None:
        if self.movie is None:
            self._movie_frame_cache.clear()
            return
        self.movie.stop()
        self.artwork.clear()
        self._movie_frame_cache.clear()
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
