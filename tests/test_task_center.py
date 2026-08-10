from __future__ import annotations

import threading
import time
from pathlib import Path

from ai_material_preprocessor.errors import ErrorCode, UserFacingError
from ai_material_preprocessor.infrastructure.processes import CancellationToken
from ai_material_preprocessor.models import Job, Operation, TaskStatus
from ai_material_preprocessor.services.job_executor import TaskExecutionResult
from ai_material_preprocessor.services.task_center import TaskCenter
from ai_material_preprocessor.services.task_repository import PersistentTaskQueue


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute_one(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress=None,
    ) -> TaskExecutionResult:
        self.calls.append(job.source.name)
        if on_progress:
            on_progress(40, "处理中")
        if "broken" in job.source.name:
            raise UserFacingError(
                ErrorCode.CONVERSION_FAILED,
                "测试转换失败",
                retryable=True,
            )
        return TaskExecutionResult(job.output_root / f"{job.source.stem}.out", ())


class BlockingExecutor:
    def __init__(self) -> None:
        self.started = threading.Event()

    def execute_one(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress=None,
    ) -> TaskExecutionResult:
        assert cancellation is not None
        self.started.set()
        while not cancellation.is_cancelled:
            time.sleep(0.005)
        raise UserFacingError(ErrorCode.CANCELLED, "任务已取消。", retryable=True)


class ChattyExecutor:
    def execute_one(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress=None,
    ) -> TaskExecutionResult:
        for percent in range(1, 100):
            on_progress(percent, f"{percent}%")
        return TaskExecutionResult(job.output_root / "done.md", ())


class CountingQueue(PersistentTaskQueue):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.save_count = 0

    def save(self, tasks):
        self.save_count += 1
        super().save(tasks)


def _job(tmp_path: Path, name: str) -> Job:
    source = tmp_path / name
    source.write_bytes(b"input")
    return Job(source, Operation.TO_MARKDOWN, tmp_path / "输出 目录")


def test_task_center_isolates_failures_and_persists_per_item_progress(tmp_path: Path) -> None:
    repository = PersistentTaskQueue(tmp_path / "state.json")
    updates: list[tuple[str, TaskStatus, int]] = []
    overall: list[int] = []
    executor = FakeExecutor()
    center = TaskCenter(
        repository,
        executor,
        on_task_changed=lambda task: updates.append(
            (task.job.source.name, task.status, task.progress)
        ),
        on_overall_progress=overall.append,
    )
    center.enqueue(
        [
            _job(tmp_path, "one.docx"),
            _job(tmp_path, "broken.docx"),
            _job(tmp_path, "two.docx"),
        ]
    )

    result = center.run()

    assert executor.calls == ["one.docx", "broken.docx", "two.docx"]
    assert [task.status for task in result] == [
        TaskStatus.SUCCESS,
        TaskStatus.FAILED,
        TaskStatus.SUCCESS,
    ]
    assert result[0].progress == 100
    assert result[0].started_at is not None
    assert result[0].finished_at is not None
    assert result[0].finished_at >= result[0].started_at
    assert result[1].error == "测试转换失败"
    assert overall[-1] == 100
    assert any(status is TaskStatus.RUNNING and progress == 40 for _, status, progress in updates)
    assert repository.load() == result


def test_cancel_waiting_task_prevents_execution(tmp_path: Path) -> None:
    executor = FakeExecutor()
    center = TaskCenter(PersistentTaskQueue(tmp_path / "state.json"), executor)
    tasks = center.enqueue([_job(tmp_path, "one.docx"), _job(tmp_path, "two.docx")])

    assert center.cancel(tasks[1].task_id)
    result = center.run()

    assert executor.calls == ["one.docx"]
    assert result[1].status is TaskStatus.CANCELLED


def test_cancel_running_task_signals_shared_cancellation_token(tmp_path: Path) -> None:
    executor = BlockingExecutor()
    center = TaskCenter(PersistentTaskQueue(tmp_path / "state.json"), executor)
    task = center.enqueue([_job(tmp_path, "long.docx")])[0]
    thread = threading.Thread(target=center.run)
    thread.start()
    assert executor.started.wait(timeout=1)

    assert center.cancel(task.task_id)
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert center.tasks[0].status is TaskStatus.CANCELLED


def test_retry_resets_failed_interrupted_or_cancelled_tasks(tmp_path: Path) -> None:
    executor = FakeExecutor()
    center = TaskCenter(PersistentTaskQueue(tmp_path / "state.json"), executor)
    failed = center.enqueue([_job(tmp_path, "broken.docx")])[0]
    center.run()
    assert center.tasks[0].status is TaskStatus.FAILED

    retried = center.retry([failed.task_id])

    assert len(retried) == 1
    assert retried[0].status is TaskStatus.WAITING
    assert retried[0].progress == 0
    assert retried[0].error == ""
    assert retried[0].attempts == 1


def test_frequent_progress_updates_are_persisted_in_bounded_steps(tmp_path: Path) -> None:
    repository = CountingQueue(tmp_path / "state.json")
    center = TaskCenter(repository, ChattyExecutor())
    center.enqueue([_job(tmp_path, "long.docx")])

    center.run()

    assert center.tasks[0].progress == 100
    assert repository.load()[0].progress == 100
    assert repository.save_count <= 25
