from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ..converters.markdown import SUPPORTED_EXTENSIONS as MARKDOWN_EXTENSIONS
from ..models import ToolStatus


class CapabilityState(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    VERSION_WARNING = "version_warning"


@dataclass(frozen=True)
class ToolDescriptor:
    display_name: str
    optional: bool
    custom_path_supported: bool
    installation_hint: str


@dataclass(frozen=True)
class ToolCapability:
    key: str
    display_name: str
    status: ToolStatus
    state: CapabilityState
    optional: bool
    custom_path_supported: bool
    installation_hint: str

    @property
    def status_text(self) -> str:
        optional = "可选 · " if self.optional else ""
        if self.state is CapabilityState.AVAILABLE:
            return optional + "可用"
        if self.state is CapabilityState.VERSION_WARNING:
            return optional + "版本异常"
        return optional + "未安装"


TOOL_DESCRIPTORS: dict[str, ToolDescriptor] = {
    "markitdown": ToolDescriptor(
        "Microsoft MarkItDown",
        False,
        True,
        "安装 MarkItDown，或在设置中选择 markitdown 可执行文件。",
    ),
    "ffmpeg": ToolDescriptor(
        "FFmpeg",
        False,
        True,
        "安装 FFmpeg，或选择 ffmpeg.exe；视频转换和联系表需要它。",
    ),
    "ffprobe": ToolDescriptor(
        "ffprobe",
        True,
        True,
        "ffprobe 通常随 FFmpeg 提供；用于读取视频元数据。",
    ),
    "exiftool": ToolDescriptor(
        "ExifTool",
        True,
        True,
        "ExifTool 是可选工具；用于读取拍摄时间、GPS 和设备信息。",
    ),
    "libreoffice": ToolDescriptor(
        "LibreOffice",
        True,
        True,
        "可选安装 LibreOffice；Microsoft Office 不可用时用于 Word/PPT 转 PDF。",
    ),
    "winword": ToolDescriptor(
        "Microsoft Word",
        True,
        True,
        "可选安装 Microsoft Word，或指定 WINWORD.EXE。",
    ),
    "powerpoint": ToolDescriptor(
        "Microsoft PowerPoint",
        True,
        True,
        "可选安装 Microsoft PowerPoint，或指定 POWERPNT.EXE。",
    ),
    "rapidocr": ToolDescriptor(
        "本地 OCR",
        True,
        False,
        "OCR 是可选能力；官方发布包内置，源码运行可安装 RapidOCR 与 ONNX Runtime。",
    ),
}


def build_tool_capabilities(tools: dict[str, ToolStatus]) -> tuple[ToolCapability, ...]:
    capabilities: list[ToolCapability] = []
    for key, descriptor in TOOL_DESCRIPTORS.items():
        status = tools.get(key, ToolStatus(key, None))
        if not status.available:
            state = CapabilityState.MISSING
        elif status.detail and re.search(r"版本|version|probe|检测失败", status.detail, re.I):
            state = CapabilityState.VERSION_WARNING
        else:
            state = CapabilityState.AVAILABLE
        capabilities.append(
            ToolCapability(
                key,
                descriptor.display_name,
                status,
                state,
                descriptor.optional,
                descriptor.custom_path_supported,
                descriptor.installation_hint,
            )
        )
    return tuple(capabilities)


def missing_feature_guidance(suffix: str, tools: dict[str, ToolStatus]) -> str:
    suffix = suffix.lower()
    if (
        suffix in MARKDOWN_EXTENSIONS
        and not tools.get("markitdown", ToolStatus("markitdown", None)).available
    ):
        return TOOL_DESCRIPTORS["markitdown"].installation_hint
    return ""
