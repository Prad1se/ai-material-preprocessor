from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ...application.executor_registry import TaskExecutionResult
from ...infrastructure.processes import CancellationToken
from ...models import Job


class DocumentService(Protocol):
    def convert(
        self,
        job: Job,
        *,
        cancellation: CancellationToken | None = None,
    ) -> tuple[Path, list[dict]]: ...


class DocumentOperationExecutor:
    def __init__(self, service: DocumentService) -> None:
        self.service = service

    def execute(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress=None,
    ) -> TaskExecutionResult:
        del index, on_progress
        output, reports = self.service.convert(job, cancellation=cancellation)
        return TaskExecutionResult(output, tuple(reports))
