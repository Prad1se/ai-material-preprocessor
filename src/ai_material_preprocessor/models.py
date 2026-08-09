from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Operation(StrEnum):
    TO_MARKDOWN = "生成 AI 资料包 / Markdown"
    TO_PDF = "转为 PDF"
    COMPRESS_VIDEO = "压缩视频"
    EXTRACT_AUDIO = "提取音频"
    STANDARDIZE_MP4 = "标准化为 MP4"
    KEYFRAMES_CONTACT_SHEET = "提取关键帧和联系表"
    RENAME_VIDEO = "按拍摄时间/地点命名"


class TaskStatus(StrEnum):
    WAITING = "waiting"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"

    @property
    def is_terminal(self) -> bool:
        return self not in {TaskStatus.WAITING, TaskStatus.RUNNING}


@dataclass(frozen=True)
class ToolStatus:
    name: str
    path: str | None
    source: str = ""
    version: str = ""
    detail: str = ""

    @property
    def available(self) -> bool:
        return bool(self.path)


@dataclass(frozen=True)
class Job:
    source: Path
    operation: Operation
    output_root: Path
    location: str = ""
