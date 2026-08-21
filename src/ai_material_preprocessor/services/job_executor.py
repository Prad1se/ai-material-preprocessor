from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..application.default_registry import build_default_executor_registry
from ..application.executor_registry import OperationExecutorRegistry, TaskExecutionResult
from ..apps.documents.executor import DocumentService
from ..apps.video.executor import VideoService
from ..errors import UserFacingError, explain_error
from ..infrastructure.processes import CancellationToken
from ..models import Job, TaskStatus, ToolStatus
from .document_service import DocumentConversionService
from .task_manifest import TaskRecord
from .video_service import VideoProcessingService


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


ProgressCallback = Callable[[int, int, str], None]


class JobExecutor:
    def __init__(
        self,
        *,
        tools: dict[str, ToolStatus],
        config: dict,
        document_service: DocumentService | None = None,
        video_service: VideoService | None = None,
        registry: OperationExecutorRegistry | None = None,
    ) -> None:
        if registry is not None:
            self.registry = registry
            return
        documents = document_service or DocumentConversionService(tools, config)
        video = video_service or VideoProcessingService(tools, config)
        self.registry = build_default_executor_registry(documents, video)

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
        result = self.registry.execute(
            job,
            index,
            cancellation=cancellation,
            on_progress=on_progress,
        )
        self._raise_if_cancelled(cancellation)
        if on_progress:
            on_progress(95, f"正在完成：{job.source.name}")
        return result

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
