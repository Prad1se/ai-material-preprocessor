from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QThread, Signal

from ..errors import explain_error
from ..models import Job, ToolStatus
from ..services.job_executor import BatchExecutionResult, JobExecutor
from ..services.task_manifest import (
    TaskRecord,
    resolve_history_root,
    write_task_manifest,
)


class Executor(Protocol):
    def execute_batch(self, jobs: list[Job], *, on_progress) -> BatchExecutionResult: ...


HistoryWriter = Callable[[Path, list[TaskRecord]], object]


class Worker(QThread):
    """Translate application-service callbacks into Qt signals only."""

    progress = Signal(int, str)
    completed = Signal(list, list, list)
    failed = Signal(str)

    def __init__(
        self,
        jobs: list[Job],
        tools: dict[str, ToolStatus],
        config: dict,
        *,
        executor: Executor | None = None,
        history_root: Path | None = None,
        history_writer: HistoryWriter = write_task_manifest,
    ) -> None:
        super().__init__()
        self.jobs = jobs
        self.executor = executor or JobExecutor(tools=tools, config=config)
        self.history_root = history_root or resolve_history_root(config)
        self.history_writer = history_writer

    def _on_progress(self, completed: int, total: int, message: str) -> None:
        percent = round(completed / total * 100) if total else 100
        self.progress.emit(percent, message)

    def run(self) -> None:
        try:
            result = self.executor.execute_batch(
                self.jobs,
                on_progress=self._on_progress,
            )
            errors = [
                f"{failure.source.name}：{failure.error.user_message}"
                for failure in result.failures
            ]
            try:
                self.history_writer(self.history_root, list(result.records))
            except OSError as exc:
                errors.append(f"历史记录：{explain_error(exc, action='保存历史记录')}")
            self.completed.emit(
                [str(path) for path in result.outputs],
                errors,
                list(result.quality_reports),
            )
        except Exception as exc:
            self.failed.emit(str(explain_error(exc, action="执行任务")))
