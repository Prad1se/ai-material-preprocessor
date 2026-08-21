from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..infrastructure.processes import CancellationToken
from ..models import Job, Operation


@dataclass(frozen=True)
class TaskExecutionResult:
    output: Path
    quality_reports: tuple[dict, ...] = ()


class OperationExecutor(Protocol):
    def execute(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> TaskExecutionResult: ...


class UnregisteredOperationError(ValueError):
    def __init__(self, operation: Operation) -> None:
        super().__init__(f"No executor is registered for operation {operation.name}.")
        self.operation = operation


class OperationExecutorRegistry:
    """Dispatch jobs to injected operation executors without knowing their domains."""

    def __init__(
        self,
        executors: Mapping[Operation, OperationExecutor] | None = None,
    ) -> None:
        self._executors: dict[Operation, OperationExecutor] = dict(executors or {})

    def register(
        self,
        operations: Iterable[Operation],
        executor: OperationExecutor,
    ) -> None:
        for operation in operations:
            if operation in self._executors:
                raise ValueError(f"An executor is already registered for {operation.name}.")
            self._executors[operation] = executor

    def execute(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> TaskExecutionResult:
        executor = self._executors.get(job.operation)
        if executor is None:
            raise UnregisteredOperationError(job.operation)
        return executor.execute(
            job,
            index,
            cancellation=cancellation,
            on_progress=on_progress,
        )
