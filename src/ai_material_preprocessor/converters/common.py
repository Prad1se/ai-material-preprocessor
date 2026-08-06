from __future__ import annotations

import subprocess
from pathlib import Path


class ConversionError(RuntimeError):
    pass


def run_command(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "未知错误").strip()
        raise ConversionError(detail)
    return result
