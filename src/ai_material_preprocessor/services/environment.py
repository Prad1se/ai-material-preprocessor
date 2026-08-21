from __future__ import annotations

import shutil
import sys
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..models import ToolStatus

OFFICE_DEFAULTS = {
    "winword": [
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
    ],
    "powerpoint": [
        r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE",
    ],
    "libreoffice": [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ],
}

TOOL_LOCATIONS: dict[str, list[tuple[str, ...]]] = {
    "ffmpeg": [("ffmpeg", "bin", "ffmpeg.exe")],
    "ffprobe": [("ffmpeg", "bin", "ffprobe.exe")],
    "exiftool": [
        ("exiftool", "exiftool.exe"),
        ("exiftool", "exiftool(-k).exe"),
    ],
    "libreoffice": [("libreoffice", "program", "soffice.exe")],
}


def candidate_paths(
    name: str,
    project_root: Path,
    runtime_root: Path | None,
    managed_root: Path | None = None,
) -> list[Path]:
    roots = [root for root in (runtime_root, project_root) if root is not None]
    candidates = [
        root / "tools" / Path(*relative)
        for root in roots
        for relative in TOOL_LOCATIONS.get(name, [])
    ]
    if managed_root and managed_root.is_dir():
        filenames = {
            "ffmpeg": ("ffmpeg.exe",),
            "ffprobe": ("ffprobe.exe",),
            "exiftool": ("exiftool.exe", "exiftool(-k).exe"),
            "libreoffice": ("soffice.exe",),
        }.get(name, ())
        managed = sorted(
            (path for filename in filenames for path in managed_root.glob(f"{name}/**/{filename}")),
            reverse=True,
        )
        candidates = [*managed, *candidates]
    return candidates


def resolve_tool(
    name: str,
    override: str,
    bundled_candidates: list[Path],
    path_lookup: Callable[[str], str | None] = shutil.which,
) -> ToolStatus:
    if override and Path(override).is_file():
        return ToolStatus(name=name, path=str(Path(override)), source="配置")
    for candidate in bundled_candidates:
        if candidate.is_file():
            return ToolStatus(name=name, path=str(candidate), source="随程序提供")
    discovered = path_lookup(name)
    if discovered:
        return ToolStatus(name=name, path=discovered, source="系统 PATH")
    return ToolStatus(name=name, path=None)


def resolve_ffmpeg(
    override: str,
    bundled_candidates: list[Path],
    path_lookup: Callable[[str], str | None] = shutil.which,
    imageio_getter: Callable[[], str] | None = None,
) -> ToolStatus:
    status = resolve_tool("ffmpeg", override, bundled_candidates, path_lookup)
    if status.available:
        return status
    if imageio_getter is None:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe

            imageio_getter = get_ffmpeg_exe
        except ImportError:
            imageio_getter = None
    if imageio_getter is not None:
        try:
            path = imageio_getter()
            if path and Path(path).is_file():
                return ToolStatus("ffmpeg", path, source="imageio-ffmpeg")
        except RuntimeError:
            pass
    return status


def detect_tools(config: dict[str, Any]) -> dict[str, ToolStatus]:
    from .config import PROJECT_ROOT
    from .tool_installer import configured_tool_install_root

    overrides = config.get("tools", {})
    managed_root = configured_tool_install_root(config)
    runtime_root = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else None
    result: dict[str, ToolStatus] = {}

    markitdown_override = str(overrides.get("markitdown", ""))
    if markitdown_override and Path(markitdown_override).is_file():
        result["markitdown"] = resolve_tool("markitdown", markitdown_override, [], shutil.which)
    else:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Couldn't find ffmpeg or avconv.*")
                import markitdown  # noqa: F401

            result["markitdown"] = ToolStatus(
                name="markitdown", path="Python API", source="内置 Python 包"
            )
        except ImportError:
            result["markitdown"] = resolve_tool("markitdown", markitdown_override, [], shutil.which)

    try:
        import onnxruntime  # noqa: F401
        import rapidocr  # noqa: F401

        result["rapidocr"] = ToolStatus(name="rapidocr", path="Python API", source="内置本地 OCR")
    except ImportError:
        result["rapidocr"] = ToolStatus(name="rapidocr", path=None)

    result["ffmpeg"] = resolve_ffmpeg(
        overrides.get("ffmpeg", ""),
        candidate_paths("ffmpeg", PROJECT_ROOT, runtime_root, managed_root),
        shutil.which,
    )

    for name in ("ffprobe", "exiftool"):
        result[name] = resolve_tool(
            name,
            overrides.get(name, ""),
            candidate_paths(name, PROJECT_ROOT, runtime_root, managed_root),
            shutil.which,
        )

    for name in ("libreoffice", "winword", "powerpoint"):
        bundled = candidate_paths(name, PROJECT_ROOT, runtime_root, managed_root)
        bundled.extend(Path(path) for path in OFFICE_DEFAULTS[name])
        status = resolve_tool(name, overrides.get(name, ""), bundled, shutil.which)
        if status.path and any(
            Path(status.path) == Path(default) for default in OFFICE_DEFAULTS[name]
        ):
            status = ToolStatus(name, status.path, source="本机安装")
        result[name] = status

    return result


def select_tools(
    tools: dict[str, ToolStatus],
    names: set[str] | frozenset[str],
) -> dict[str, ToolStatus]:
    """Return the detected tool view relevant to one application boundary."""
    return {name: tools[name] for name in names if name in tools}
