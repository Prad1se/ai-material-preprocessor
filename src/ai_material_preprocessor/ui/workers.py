from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..application.task_runner import (
    ApplicationTaskRunner,
    Executor,
    HistoryWriter,
    Preflight,
)
from ..errors import explain_error
from ..models import Job, QueuedTask, ToolStatus
from ..services.task_manifest import write_task_manifest
from ..services.task_repository import PersistentTaskQueue


class Worker(QThread):
    """Adapt the Qt-independent application runner to Qt thread signals."""

    progress = Signal(int, str)
    task_changed = Signal(str, str, int, str)
    completed = Signal(list, list, list)
    failed = Signal(str)

    def __init__(
        self,
        jobs: list[Job],
        tools: dict[str, ToolStatus],
        config: dict,
        *,
        executor: Executor | None = None,
        task_repository: PersistentTaskQueue | None = None,
        disk_preflight: Preflight | None = None,
        history_root: Path | None = None,
        history_writer: HistoryWriter = write_task_manifest,
    ) -> None:
        super().__init__()
        self.runner = ApplicationTaskRunner(
            jobs,
            tools,
            config,
            executor=executor,
            task_repository=task_repository,
            disk_preflight=disk_preflight,
            history_root=history_root,
            history_writer=history_writer,
            on_task_changed=self._on_task_changed,
            on_progress=self.progress.emit,
        )
        # Compatibility aliases keep the v2.0 GUI and tests stable while orchestration lives outside Qt.
        self.config = self.runner.config
        self.tools = self.runner.tools
        self.executor = self.runner.executor
        self.task_repository = self.runner.task_repository
        self.disk_preflight = self.runner.disk_preflight
        self.history_root = self.runner.history_root
        self.history_writer = self.runner.history_writer
        self.center = self.runner.center
        self.tracked_ids = self.runner.tracked_ids
        self.batch_ids = self.runner.batch_ids

    @property
    def tasks(self) -> list[QueuedTask]:
        return self.runner.tasks

    def _on_task_changed(self, task: QueuedTask) -> None:
        self.task_changed.emit(
            task.task_id,
            task.status.value,
            task.progress,
            task.message or task.error,
        )

    def cancel_task(self, task_id: str) -> bool:
        return self.runner.cancel_task(task_id)

    def retry_tasks(self, task_ids: list[str]) -> list[QueuedTask]:
        return self.runner.retry_tasks(task_ids)

    def run(self) -> None:
        try:
            result = self.runner.run()
            self.completed.emit(
                [str(path) for path in result.outputs],
                list(result.errors),
                list(result.quality_reports),
            )
        except Exception as exc:
            self.failed.emit(str(explain_error(exc, action="执行任务")))
