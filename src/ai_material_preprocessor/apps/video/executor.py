from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from ...application.executor_registry import TaskExecutionResult
from ...infrastructure.processes import CancellationToken
from ...models import Job


class VideoService(Protocol):
    def convert(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> Path: ...


class VideoOperationExecutor:
    def __init__(self, service: VideoService) -> None:
        self.service = service

    def execute(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> TaskExecutionResult:
        output = self.service.convert(
            job,
            index,
            cancellation=cancellation,
            on_progress=on_progress,
        )
        return TaskExecutionResult(output)


class VideoAIPackService(Protocol):
    def create_pack(
        self,
        job: Job,
        index: int = 1,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> Any: ...


class VideoAIPackOperationExecutor:
    def __init__(self, service: VideoAIPackService) -> None:
        self.service = service

    def execute(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> TaskExecutionResult:
        result = self.service.create_pack(
            job,
            index,
            cancellation=cancellation,
            on_progress=on_progress,
        )
        return TaskExecutionResult(result.output, (result.report,))
