from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..errors import UserFacingError, explain_error
from ..models import Job, Operation, TaskStatus, ToolStatus
from .document_service import DocumentConversionService
from .task_manifest import TaskRecord
from .video_service import VideoProcessingService


class DocumentService(Protocol):
    def convert(self, job: Job) -> tuple[Path, list[dict]]: ...


class VideoService(Protocol):
    def convert(self, job: Job, index: int) -> Path: ...


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
    ) -> None:
        self.document_service = document_service or DocumentConversionService(tools, config)
        self.video_service = video_service or VideoProcessingService(tools, config)

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
                if job.operation in {Operation.TO_MARKDOWN, Operation.TO_PDF}:
                    output, job_reports = self.document_service.convert(job)
                    reports.extend(job_reports)
                else:
                    output = self.video_service.convert(job, index)
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
