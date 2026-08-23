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
    DOCUMENT_CONTEXT_PACK = "生成 Context Pack"


# 唯一的用户可见操作中文标签：历史、任务中心、工作区共用这一份映射。
OPERATION_LABELS: dict[Operation, str] = {
    Operation.TO_MARKDOWN: "AI 就绪 Markdown",
    Operation.TO_PDF: "创建 PDF 副本",
    Operation.COMPRESS_VIDEO: "压缩视频",
    Operation.EXTRACT_AUDIO: "提取音频",
    Operation.STANDARDIZE_MP4: "标准化为 MP4",
    Operation.KEYFRAMES_CONTACT_SHEET: "提取关键帧和联系表",
    Operation.RENAME_VIDEO: "按拍摄时间/地点命名",
    Operation.ORGANIZE_VIDEO: "按日期/地点整理",
    Operation.DOCUMENT_CONTEXT_PACK: "AI 上下文包",
}

# 旧枚举原值到新标签的反查，兼容历史记录或调用方仍传入原值的情况。
_OPERATION_LABELS_BY_VALUE = {
    operation.value: label for operation, label in OPERATION_LABELS.items()
}


def operation_display(operation: Operation | str) -> str:
    """Return the unified Chinese display label for an operation.

    Accepts an ``Operation`` member, its ``name``, or its legacy enum value so
    persisted records and stale callers keep rendering the current wording.
    """

    if isinstance(operation, Operation):
        return OPERATION_LABELS.get(operation, operation.value)
    return _OPERATION_LABELS_BY_VALUE.get(operation, operation)


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


# 唯一的任务状态中文标签：历史、任务中心、工作区共用这一份映射。
STATUS_LABELS: dict[TaskStatus, str] = {
    TaskStatus.WAITING: "等待",
    TaskStatus.RUNNING: "运行中",
    TaskStatus.SUCCESS: "成功",
    TaskStatus.FAILED: "失败",
    TaskStatus.CANCELLED: "已取消",
    TaskStatus.INTERRUPTED: "已中断",
}

_STATUS_LABELS_BY_VALUE = {status.value: label for status, label in STATUS_LABELS.items()}


def status_display(status: TaskStatus | str) -> str:
    """Return the unified Chinese display label for a task status."""

    if isinstance(status, TaskStatus):
        return STATUS_LABELS.get(status, status.value)
    return _STATUS_LABELS_BY_VALUE.get(status, status)


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
    sources: tuple[Path, ...] = ()
    context_budget: int | None = None
    context_ocr_enabled: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.sources, tuple):
            raise TypeError("Job.sources must be a tuple of Paths.")
        if any(not isinstance(path, Path) for path in self.sources):
            raise TypeError("Job.sources must contain only Paths.")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("Job.sources must not contain duplicate paths.")
        if self.source in self.sources[1:]:
            raise ValueError("Job.sources must not repeat the primary source.")
        if self.context_budget is not None and (
            isinstance(self.context_budget, bool) or not isinstance(self.context_budget, int)
        ):
            raise TypeError("Job.context_budget must be an integer or None.")
        if self.context_budget is not None and self.context_budget <= 0:
            raise ValueError("Job.context_budget must be positive.")
        if self.context_ocr_enabled is not None and not isinstance(self.context_ocr_enabled, bool):
            raise TypeError("Job.context_ocr_enabled must be a boolean or None.")

    @property
    def input_sources(self) -> tuple[Path, ...]:
        """All inputs in deterministic order, including the primary source."""

        if self.sources and self.sources[0] == self.source:
            return self.sources
        return (self.source, *self.sources)


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
