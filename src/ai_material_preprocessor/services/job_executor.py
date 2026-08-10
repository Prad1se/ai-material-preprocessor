from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..errors import UserFacingError, explain_error
from ..infrastructure.processes import CancellationToken
from ..models import Job, Operation, TaskStatus, ToolStatus
from .document_service import DocumentConversionService
from .task_manifest import TaskRecord
from .video_service import VideoProcessingService


class DocumentService(Protocol):
    def convert(
        self,
        job: Job,
        *,
        cancellation: CancellationToken | None = None,
    ) -> tuple[Path, list[dict]]: ...


class VideoService(Protocol):
    def convert(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> Path: ...


@dataclass(frozen=True)
class TaskFailure:
    source: Path
    error: UserFacingError


@dataclass(frozen=True)
class BatchExecutionResult:
    outputs: tuple[Path, ...]
    failures: tuple[TaskFailure, ...]
    quality_reports: tuple[dict, ...]
    records: tuple[TaskRecord, ...]


@dataclass(frozen=True)
class TaskExecutionResult:
    output: Path
    quality_reports: tuple[dict, ...] = ()


ProgressCallback = Callable[[int, int, str], None]


class JobExecutor:
    def __init__(
        self,
        *,
        tools: dict[str, ToolStatus],
        config: dict,
        document_service: DocumentService | None = None,
        video_service: VideoService | None = None,
    ) -> None:
        self.document_service = document_service or DocumentConversionService(tools, config)
        self.video_service = video_service or VideoProcessingService(tools, config)

    @staticmethod
    def _raise_if_cancelled(cancellation: CancellationToken | None) -> None:
        if cancellation and cancellation.is_cancelled:
            from ..errors import ErrorCode

            raise UserFacingError(
                ErrorCode.CANCELLED,
                "任务已取消，原文件没有改动。",
                retryable=True,
            )

    def execute_one(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> TaskExecutionResult:
        self._raise_if_cancelled(cancellation)
        if on_progress:
            on_progress(5, f"正在处理：{job.source.name}")
        if job.operation in {Operation.TO_MARKDOWN, Operation.TO_PDF}:
            output, job_reports = self.document_service.convert(
                job,
                cancellation=cancellation,
            )
        else:
            output = self.video_service.convert(
                job,
                index,
                cancellation=cancellation,
                on_progress=on_progress,
            )
            job_reports = []
        self._raise_if_cancelled(cancellation)
        if on_progress:
            on_progress(95, f"正在完成：{job.source.name}")
        return TaskExecutionResult(output, tuple(job_reports))

    def execute_batch(
        self,
        jobs: list[Job],
        *,
        on_progress: ProgressCallback | None = None,
    ) -> BatchExecutionResult:
        outputs: list[Path] = []
        failures: list[TaskFailure] = []
        reports: list[dict] = []
        records: list[TaskRecord] = []
        total = len(jobs)
        for index, job in enumerate(jobs, start=1):
            if on_progress:
                on_progress(index - 1, total, f"正在处理：{job.source.name}")
            try:
                execution = self.execute_one(job, index)
                output = execution.output
                reports.extend(execution.quality_reports)
                outputs.append(output)
                records.append(
                    TaskRecord(job.source, job.operation, TaskStatus.SUCCESS, output=output)
                )
            except Exception as exc:
                error = explain_error(exc, action=job.operation.value)
                failures.append(TaskFailure(job.source, error))
                records.append(
                    TaskRecord(
                        job.source,
                        job.operation,
                        TaskStatus.FAILED,
                        error=error.user_message,
                    )
                )
            if on_progress:
                on_progress(index, total, f"已处理：{job.source.name}")
        return BatchExecutionResult(tuple(outputs), tuple(failures), tuple(reports), tuple(records))
