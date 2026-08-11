from __future__ import annotations

import sys
from pathlib import Path

MOUSE_STATE_ASSETS = {
    "idle": "mouse-grin.png",
    "thinking": "mouse-thinking.png",
    "working": "mouse-thinking.png",
    "success": "mouse-strong.png",
    "error": "mouse-thinking.png",
}


def mouse_asset_path(filename: str) -> Path:
    """Resolve mascot artwork in source and PyInstaller onedir builds."""
    packaged = Path(getattr(sys, "_MEIPASS", Path.cwd())) / "assets" / "mouse" / filename
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[3] / "assets" / "mouse" / filename
