from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

from ..services.config import resource_path


def app_icon_path() -> Path:
    """Return the shared runtime icon in source and packaged builds."""
    return resource_path("assets", "app-icon.ico")


def load_app_icon() -> QIcon:
    """Load the application icon without making startup depend on the asset."""
    path = app_icon_path()
    return QIcon(str(path)) if path.is_file() else QIcon()
