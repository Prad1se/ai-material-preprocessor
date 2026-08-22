from __future__ import annotations

from PySide6.QtWidgets import QApplication, QDialog


def fit_dialog_to_available_space(
    dialog: QDialog,
    preferred_width: int,
    preferred_height: int,
    *,
    minimum_width: int,
    minimum_height: int,
    margin: int = 32,
) -> None:
    """Size a dialog for its parent window or, when standalone, the current screen."""
    parent = dialog.parentWidget()
    if parent is not None:
        available_width = parent.window().width()
        available_height = parent.window().height()
    else:
        screen = QApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen is not None else None
        available_width = geometry.width() if geometry is not None else preferred_width
        available_height = geometry.height() if geometry is not None else preferred_height
    width = max(minimum_width, min(preferred_width, available_width - margin))
    height = max(minimum_height, min(preferred_height, available_height - margin))
    dialog.setMinimumSize(minimum_width, minimum_height)
    dialog.resize(width, height)
