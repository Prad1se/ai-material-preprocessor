from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from typing import Protocol

from ..errors import ErrorCode, explain_error
from ..infrastructure.processes import CancellationToken
from ..models import Job, QueuedTask, TaskStatus
from .job_executor import TaskExecutionResult
from .task_repository import PersistentTaskQueue


class SingleJobExecutor(Protocol):
    def execute_one(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> TaskExecutionResult: ...


TaskCallback = Callable[[QueuedTask], None]
OverallCallback = Callable[[int], None]


class TaskCenter:
    """Sequential, failure-isolating scheduler with persistent item state."""

    def __init__(
        self,
        repository: PersistentTaskQueue,
        executor: SingleJobExecutor,
        *,
        on_task_changed: TaskCallback | None = None,
        on_overall_progress: OverallCallback | None = None,
    ) -> None:
        self.repository = repository
        self.executor = executor
        self.on_task_changed = on_task_changed
        self.on_overall_progress = on_overall_progress
        self._lock = threading.RLock()
        self._tasks = repository.load(recover_interrupted=True)
        self._active_tokens: dict[str, CancellationToken] = {}
        self._quality_reports: dict[str, tuple[dict, ...]] = {}
        self._persisted_progress = {task.task_id: task.progress for task in self._tasks}

    @property
    def tasks(self) -> list[QueuedTask]:
        with self._lock:
            return list(self._tasks)

    def quality_reports(self, task_ids: set[str] | None = None) -> list[dict]:
        with self._lock:
            selected = task_ids if task_ids is not None else set(self._quality_reports)
            return [
                report
                for task_id, reports in self._quality_reports.items()
                if task_id in selected
                for report in reports
            ]

    def quality_reports_for(self, task_id: str) -> tuple[dict, ...]:
        with self._lock:
            return self._quality_reports.get(task_id, ())

    def _find_index(self, task_id: str) -> int | None:
        return next(
            (index for index, task in enumerate(self._tasks) if task.task_id == task_id),
            None,
        )

    def _emit_overall(self) -> None:
        if not self.on_overall_progress:
            return
        total = len(self._tasks)
        completed = sum(task.status.is_terminal for task in self._tasks)
        self.on_overall_progress(round(completed / total * 100) if total else 100)

    def _store(self, task: QueuedTask, *, persist: bool = True) -> QueuedTask:
        with self._lock:
            index = self._find_index(task.task_id)
            if index is None:
                raise KeyError(task.task_id)
            self._tasks[index] = task
            if persist:
                self.repository.save(self._tasks)
                self._persisted_progress[task.task_id] = task.progress
        if self.on_task_changed:
            self.on_task_changed(task)
        self._emit_overall()
        return task

    def enqueue(self, jobs: list[Job]) -> list[QueuedTask]:
        now = datetime.now(UTC)
        additions = [
            QueuedTask(
                task_id=f"task-{uuid.uuid4().hex[:12]}",
                job=job,
                created_at=now,
                updated_at=now,
            )
            for job in jobs
        ]
        with self._lock:
            self._tasks.extend(additions)
            self.repository.save(self._tasks)
            self._persisted_progress.update({task.task_id: task.progress for task in additions})
        for task in additions:
            if self.on_task_changed:
                self.on_task_changed(task)
        self._emit_overall()
        return additions

    def _progress(self, task_id: str, percent: int, message: str) -> None:
        with self._lock:
            index = self._find_index(task_id)
            if index is None or self._tasks[index].status is not TaskStatus.RUNNING:
                return
            progress = min(99, max(0, percent))
            task = self._tasks[index].with_changes(
                progress=progress,
                message=message,
                updated_at=datetime.now(UTC),
            )
            last_persisted = self._persisted_progress.get(task_id, 0)
            should_persist = progress < last_persisted or progress - last_persisted >= 5
        self._store(task, persist=should_persist)

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            index = self._find_index(task_id)
            if index is None:
                return False
            task = self._tasks[index]
            if task.status is TaskStatus.WAITING:
                cancelled = task.with_changes(
                    status=TaskStatus.CANCELLED,
                    error="任务在开始前被取消。",
                    message="已取消",
                    updated_at=datetime.now(UTC),
                )
            elif task.status is TaskStatus.RUNNING:
                token = self._active_tokens.get(task_id)
                if token is None:
                    return False
                token.cancel()
                return True
            else:
                return False
        self._store(cancelled)
        return True

    def retry(self, task_ids: list[str]) -> list[QueuedTask]:
        retried: list[QueuedTask] = []
        retryable = {TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.INTERRUPTED}
        for task_id in task_ids:
            with self._lock:
                index = self._find_index(task_id)
                if index is None or self._tasks[index].status not in retryable:
                    continue
                task = self._tasks[index].with_changes(
                    status=TaskStatus.WAITING,
                    progress=0,
                    error="",
                    output=None,
                    message="等待重试",
                    started_at=None,
                    finished_at=None,
                    updated_at=datetime.now(UTC),
                )
            retried.append(self._store(task))
        return retried

    def run(self, task_ids: set[str] | None = None) -> list[QueuedTask]:
        with self._lock:
            pending_ids = [
                task.task_id
                for task in self._tasks
                if task.status is TaskStatus.WAITING
                and (task_ids is None or task.task_id in task_ids)
            ]
        for index, task_id in enumerate(pending_ids, start=1):
            with self._lock:
                current_index = self._find_index(task_id)
                if current_index is None:
                    continue
                task = self._tasks[current_index]
                if task.status is not TaskStatus.WAITING:
                    continue
                token = CancellationToken()
                self._active_tokens[task_id] = token
                started = datetime.now(UTC)
                running = task.with_changes(
                    status=TaskStatus.RUNNING,
                    progress=0,
                    attempts=task.attempts + 1,
                    error="",
                    message=f"正在处理：{task.job.source.name}",
                    updated_at=started,
                    started_at=started,
                    finished_at=None,
                )
            self._store(running)
            try:
                result = self.executor.execute_one(
                    running.job,
                    index,
                    cancellation=token,
                    on_progress=partial(self._progress, task_id),
                )
                with self._lock:
                    self._quality_reports[task_id] = result.quality_reports
                finished = datetime.now(UTC)
                final = running.with_changes(
                    status=TaskStatus.SUCCESS,
                    progress=100,
                    output=result.output,
                    message="处理完成",
                    updated_at=finished,
                    finished_at=finished,
                )
            except Exception as exc:
                error = explain_error(exc, action=running.job.operation.value)
                cancelled = error.code is ErrorCode.CANCELLED or token.is_cancelled
                finished = datetime.now(UTC)
                final = running.with_changes(
                    status=TaskStatus.CANCELLED if cancelled else TaskStatus.FAILED,
                    progress=min(self._current_progress(task_id), 99),
                    error=error.user_message,
                    message="已取消" if cancelled else "处理失败",
                    updated_at=finished,
                    finished_at=finished,
                )
            finally:
                with self._lock:
                    self._active_tokens.pop(task_id, None)
            self._store(final)
        return self.tasks

    def _current_progress(self, task_id: str) -> int:
        with self._lock:
            index = self._find_index(task_id)
            return self._tasks[index].progress if index is not None else 0
