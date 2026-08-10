from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QThread, Signal

from ..errors import explain_error
from ..models import Job, QueuedTask, TaskStatus, ToolStatus
from ..services.config import coerce_int
from ..services.disk_space import DiskSpacePreflight
from ..services.history_repository import HistoryRepository
from ..services.job_executor import JobExecutor, TaskExecutionResult
from ..services.task_center import TaskCenter
from ..services.task_manifest import TaskRecord, resolve_history_root, write_task_manifest
from ..services.task_repository import PersistentTaskQueue, resolve_task_queue_path


class Executor(Protocol):
    def execute_one(
        self,
        job: Job,
        index: int,
        *,
        cancellation=None,
        on_progress=None,
    ) -> TaskExecutionResult: ...


class Preflight(Protocol):
    def check(self, jobs: list[Job], *, safety_margin_bytes: int): ...


HistoryWriter = Callable[[Path, list[TaskRecord]], object]


class Worker(QThread):
    """Run the persistent task center and translate updates into Qt signals."""

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
        self.config = config
        self.tools = tools
        self.executor = executor or JobExecutor(tools=tools, config=config)
        self.task_repository = task_repository or PersistentTaskQueue(
            resolve_task_queue_path(config)
        )
        self.disk_preflight = disk_preflight or DiskSpacePreflight()
        self.history_root = history_root or resolve_history_root(config)
        self.history_writer = history_writer
        self.batch_ids: set[str] = set()
        self.center = TaskCenter(
            self.task_repository,
            self.executor,
            on_task_changed=self._on_task_changed,
            on_overall_progress=self._on_overall_progress,
        )
        recovered_tasks = {
            task.task_id
            for task in self.center.tasks
            if task.status in {TaskStatus.WAITING, TaskStatus.INTERRUPTED}
        }
        additions = self.center.enqueue(jobs)
        self.tracked_ids = recovered_tasks | {task.task_id for task in additions}
        self.batch_ids.update(task.task_id for task in additions)

    @property
    def tasks(self) -> list[QueuedTask]:
        return self.center.tasks

    def _on_task_changed(self, task: QueuedTask) -> None:
        self.task_changed.emit(
            task.task_id,
            task.status.value,
            task.progress,
            task.message or task.error,
        )

    def _on_overall_progress(self, _percent: int) -> None:
        batch = [task for task in self.center.tasks if task.task_id in self.batch_ids]
        if not batch:
            return
        percent = round(
            sum(100 if task.status.is_terminal else task.progress for task in batch) / len(batch)
        )
        active = next(
            (task for task in batch if task.status is TaskStatus.RUNNING),
            None,
        )
        message = active.message if active else "任务队列已更新"
        self.progress.emit(percent, message)

    def cancel_task(self, task_id: str) -> bool:
        return self.center.cancel(task_id)

    def retry_tasks(self, task_ids: list[str]) -> list[QueuedTask]:
        waiting = [
            task
            for task in self.center.tasks
            if task.task_id in task_ids and task.status is TaskStatus.WAITING
        ]
        retried = [*waiting, *self.center.retry(task_ids)]
        self.tracked_ids.update(task.task_id for task in retried)
        self.batch_ids.update(task.task_id for task in retried)
        return retried

    def _tracked_tasks(self) -> list[QueuedTask]:
        return [task for task in self.center.tasks if task.task_id in self.tracked_ids]

    def _batch_tasks(self) -> list[QueuedTask]:
        return [task for task in self.center.tasks if task.task_id in self.batch_ids]

    def _parameters_for(self, task: QueuedTask) -> dict[str, object]:
        if task.job.operation.name == "TO_MARKDOWN":
            document = self.config.get("document", {})
            return {
                key: document.get(key)
                for key in (
                    "mode",
                    "split_enabled",
                    "target_tokens",
                    "max_tokens",
                    "ocr_enabled",
                )
            }
        if task.job.operation.name == "TO_PDF":
            return {"output_type": "pdf"}
        video = self.config.get("video", {})
        keys_by_operation = {
            "COMPRESS_VIDEO": ("compression_crf", "compression_preset"),
            "EXTRACT_AUDIO": ("audio_format", "audio_bitrate"),
            "STANDARDIZE_MP4": (),
            "KEYFRAMES_CONTACT_SHEET": (
                "scene_threshold",
                "max_keyframes",
                "contact_sheet_columns",
            ),
            "RENAME_VIDEO": ("rename_template",),
        }
        parameters = {
            key: video.get(key) for key in keys_by_operation.get(task.job.operation.name, ())
        }
        if task.job.location:
            parameters["location_override"] = task.job.location
        return parameters

    def _tool_versions_for(self, task: QueuedTask) -> dict[str, str]:
        relevant = (
            ("markitdown", "rapidocr")
            if task.job.operation.name == "TO_MARKDOWN"
            else ("libreoffice", "winword", "powerpoint")
            if task.job.operation.name == "TO_PDF"
            else ("ffmpeg", "ffprobe", "exiftool")
        )
        return {
            name: status.version
            for name in relevant
            if (status := self.tools.get(name)) is not None and status.version
        }

    def run(self) -> None:
        try:
            for task in self._tracked_tasks():
                self._on_task_changed(task)
            waiting = [
                task.job
                for task in self.center.tasks
                if task.task_id in self.batch_ids and task.status is TaskStatus.WAITING
            ]
            safety_mb = coerce_int(
                self.config.get("task_center", {}).get("disk_space_safety_mb"),
                512,
                minimum=0,
            )
            if waiting:
                self.disk_preflight.check(
                    waiting,
                    safety_margin_bytes=max(0, safety_mb) * 1024 * 1024,
                )
            self.center.run(self.batch_ids)
            tasks = self._batch_tasks()
            records = [
                TaskRecord(
                    task.job.source,
                    task.job.operation,
                    task.status,
                    output=task.output,
                    error=task.error,
                    attempts=task.attempts,
                    started_at=task.started_at,
                    finished_at=task.finished_at,
                    parameters=self._parameters_for(task),
                    tool_versions=self._tool_versions_for(task),
                )
                for task in tasks
                if task.status.is_terminal
            ]
            errors = [
                f"{task.job.source.name}：{task.error}"
                for task in tasks
                if task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.INTERRUPTED}
            ]
            outputs = [str(task.output) for task in tasks if task.output is not None]
            if records:
                try:
                    self.history_writer(self.history_root, records)
                except OSError as exc:
                    errors.append(f"历史记录：{explain_error(exc, action='保存历史记录')}")
                history_config = self.config.get("history", {})
                try:
                    HistoryRepository(self.history_root).cleanup(
                        retention_days=coerce_int(
                            history_config.get("retention_days"),
                            90,
                            minimum=0,
                        ),
                        max_bytes=coerce_int(
                            history_config.get("max_size_mb"),
                            512,
                            minimum=0,
                        )
                        * 1024
                        * 1024,
                    )
                except OSError as exc:
                    errors.append(f"历史清理：{explain_error(exc, action='清理历史记录')}")
            reports = self.center.quality_reports(self.batch_ids)
            self.completed.emit(outputs, errors, reports)
            self.task_repository.save(
                [
                    task
                    for task in self.center.tasks
                    if task.status
                    in {TaskStatus.WAITING, TaskStatus.RUNNING, TaskStatus.INTERRUPTED}
                ]
            )
        except Exception as exc:
            self.failed.emit(str(explain_error(exc, action="执行任务")))
