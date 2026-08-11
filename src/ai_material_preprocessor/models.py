from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class Operation(StrEnum):
    TO_MARKDOWN = "生成 AI 资料包 / Markdown"
    TO_PDF = "转为 PDF"
    COMPRESS_VIDEO = "压缩视频"
    EXTRACT_AUDIO = "提取音频"
    STANDARDIZE_MP4 = "标准化为 MP4"
    KEYFRAMES_CONTACT_SHEET = "提取关键帧和联系表"
    RENAME_VIDEO = "按拍摄时间/地点命名"
    ORGANIZE_VIDEO = "按日期/地点整理"


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
    project: str = ""


@dataclass(frozen=True)
class QueuedTask:
    """Persistable state for one independently executable job."""

    task_id: str
    job: Job
    status: TaskStatus = TaskStatus.WAITING
    progress: int = 0
    attempts: int = 0
    error: str = ""
    output: Path | None = None
    message: str = ""
    created_at: datetime = datetime.min.replace(tzinfo=UTC)
    updated_at: datetime = datetime.min.replace(tzinfo=UTC)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, TaskStatus):
            object.__setattr__(self, "status", TaskStatus(self.status))
        object.__setattr__(self, "progress", min(100, max(0, int(self.progress))))

    def with_changes(self, **changes: Any) -> QueuedTask:
        return replace(self, **changes)
