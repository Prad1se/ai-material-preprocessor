from __future__ import annotations

import re
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from ..infrastructure.processes import CommandRequest, ProcessRunner
from ..models import ToolStatus
from .environment import detect_tools

PACKAGE_NAMES = {"markitdown": "markitdown", "rapidocr": "rapidocr"}
VERSION_ARGUMENTS = {
    "markitdown": ("--version",),
    "ffmpeg": ("-version",),
    "ffprobe": ("-version",),
    "exiftool": ("-ver",),
    "libreoffice": ("--version",),
}
MINIMUM_VERSIONS = {
    "markitdown": (0, 1, 6),
    "rapidocr": (3, 9),
    "ffmpeg": (5, 0),
    "ffprobe": (5, 0),
}


def _version_tuple(raw: str) -> tuple[int, ...]:
    match = re.search(r"(?<!\d)(\d+)(?:\.(\d+))?(?:\.(\d+))?", raw)
    if not match:
        return ()
    return tuple(int(part) for part in match.groups(default="0"))


def _is_below_minimum(name: str, raw_version: str) -> bool:
    minimum = MINIMUM_VERSIONS.get(name)
    detected = _version_tuple(raw_version)
    if not minimum or not detected:
        return False
    width = max(len(minimum), len(detected))
    return detected + (0,) * (width - len(detected)) < minimum + (0,) * (width - len(minimum))


def inspect_tool_versions(
    tools: dict[str, ToolStatus],
    *,
    runner: ProcessRunner | None = None,
    package_lookup: Callable[[str], str] = package_version,
) -> dict[str, ToolStatus]:
    """Enrich detected tools without changing their executable selection."""
    active_runner = runner or ProcessRunner()
    enriched: dict[str, ToolStatus] = {}
    for name, status in tools.items():
        if not status.available:
            enriched[name] = status
            continue
        raw_version = status.version
        detail = status.detail
        try:
            if status.path == "Python API" and name in PACKAGE_NAMES:
                raw_version = package_lookup(PACKAGE_NAMES[name])
            elif name in VERSION_ARGUMENTS and status.path:
                executable = status.path
                if name == "libreoffice":
                    console_executable = Path(status.path).with_suffix(".com")
                    if console_executable.is_file():
                        executable = str(console_executable)
                result = active_runner.run(
                    CommandRequest(
                        executable,
                        VERSION_ARGUMENTS[name],
                        tool_name=name,
                        timeout_seconds=5,
                    )
                )
                lines = (result.stdout or result.stderr).strip().splitlines()
                raw_version = lines[0] if lines else ""
                if not raw_version:
                    detail = "版本检测失败：工具未返回版本信息"
            elif name in {"winword", "powerpoint"}:
                raw_version = "由 Microsoft Office 管理"
        except (OSError, RuntimeError, PackageNotFoundError) as exc:
            try:
                message = str(exc)
            except Exception:
                message = type(exc).__name__
            detail = f"版本检测失败：{message or type(exc).__name__}"
        if raw_version and _is_below_minimum(name, raw_version):
            detail = f"版本异常：{raw_version} 低于建议的最低版本"
        enriched[name] = ToolStatus(
            name=status.name,
            path=status.path,
            source=status.source,
            version=raw_version,
            detail=detail,
        )
    return enriched


def detect_tools_with_versions(config: dict) -> dict[str, ToolStatus]:
    return inspect_tool_versions(detect_tools(config))
