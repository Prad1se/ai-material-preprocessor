from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_material_preprocessor.application.task_runner import ApplicationTaskRunner
from ai_material_preprocessor.errors import ErrorCode, UserFacingError
from ai_material_preprocessor.infrastructure.processes import CancellationToken
from ai_material_preprocessor.models import Job, Operation, QueuedTask, TaskStatus, ToolStatus
from ai_material_preprocessor.services.job_executor import TaskExecutionResult
from ai_material_preprocessor.services.task_repository import PersistentTaskQueue


class FakeExecutor:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[Job] = []

    def execute_one(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress=None,
    ) -> TaskExecutionResult:
        self.calls.append(job)
        if on_progress:
            on_progress(50, "处理中")
        if self.fail:
            raise UserFacingError(
                ErrorCode.CONVERSION_FAILED,
                "转换失败，请检查文件。",
                technical_detail=str(job.source),
                retryable=True,
            )
        return TaskExecutionResult(job.output_root / f"{job.source.stem}.out", ({"score": 100},))


class FailingPreflight:
    def check(self, jobs, *, safety_margin_bytes):
        raise UserFacingError(ErrorCode.FILE_SYSTEM, "输出目录空间不足。", retryable=True)


def empty_tools() -> dict[str, ToolStatus]:
    return {}


def test_application_runner_executes_without_qapplication_and_persists_history(
    tmp_path: Path,
) -> None:
    source = tmp_path / "lesson.docx"
    source.write_bytes(b"docx")
    written = []
    updates: list[QueuedTask] = []
    progress: list[tuple[int, str]] = []
    runner = ApplicationTaskRunner(
        [Job(source, Operation.TO_MARKDOWN, tmp_path / "out")],
        empty_tools(),
        {"task_center": {"disk_space_safety_mb": 0}},
        executor=FakeExecutor(),
        task_repository=PersistentTaskQueue(tmp_path / "state.json"),
        history_root=tmp_path / "history",
        history_writer=lambda root, records: written.append((root, records)),
        on_task_changed=updates.append,
        on_progress=lambda value, message: progress.append((value, message)),
    )

    result = runner.run()

    assert result.outputs == (tmp_path / "out" / "lesson.out",)
    assert result.errors == ()
    assert result.quality_reports == ({"score": 100},)
    assert updates[-1].status is TaskStatus.SUCCESS
    assert progress[-1][0] == 100
    assert written[0][1][0].quality_summary["score"] == 100
    assert runner.task_repository.load() == []


def test_application_runner_preserves_safe_failure_and_failure_isolation(tmp_path: Path) -> None:
    source = tmp_path / "private.docx"
    source.write_bytes(b"docx")
    runner = ApplicationTaskRunner(
        [Job(source, Operation.TO_MARKDOWN, tmp_path / "out")],
        empty_tools(),
        {"task_center": {"disk_space_safety_mb": 0}},
        executor=FakeExecutor(fail=True),
        task_repository=PersistentTaskQueue(tmp_path / "state.json"),
        history_root=tmp_path / "history",
        history_writer=lambda root, records: None,
    )

    result = runner.run()

    assert result.errors == ("private.docx：转换失败，请检查文件。",)
    assert str(source) not in result.errors[0]
    assert runner.tasks[0].status is TaskStatus.FAILED


def test_application_runner_checks_disk_before_execution(tmp_path: Path) -> None:
    source = tmp_path / "large.mp4"
    source.write_bytes(b"video")
    executor = FakeExecutor()
    runner = ApplicationTaskRunner(
        [Job(source, Operation.STANDARDIZE_MP4, tmp_path / "out")],
        empty_tools(),
        {"task_center": {"disk_space_safety_mb": 512}},
        executor=executor,
        task_repository=PersistentTaskQueue(tmp_path / "state.json"),
        disk_preflight=FailingPreflight(),
        history_root=tmp_path / "history",
        history_writer=lambda root, records: None,
    )

    with pytest.raises(UserFacingError, match="输出目录空间不足"):
        runner.run()

    assert executor.calls == []
    assert runner.tasks[0].status is TaskStatus.WAITING


def test_application_runner_does_not_run_recovered_work_without_explicit_retry(
    tmp_path: Path,
) -> None:
    repository = PersistentTaskQueue(tmp_path / "state.json")
    recovered_source = tmp_path / "recovered.docx"
    recovered_source.write_bytes(b"docx")
    now = datetime(2026, 8, 10, tzinfo=UTC)
    repository.save(
        [
            QueuedTask(
                "recovered",
                Job(recovered_source, Operation.TO_MARKDOWN, tmp_path / "out"),
                status=TaskStatus.WAITING,
                created_at=now,
                updated_at=now,
            )
        ]
    )
    new_source = tmp_path / "new.docx"
    new_source.write_bytes(b"docx")
    executor = FakeExecutor()
    runner = ApplicationTaskRunner(
        [Job(new_source, Operation.TO_MARKDOWN, tmp_path / "out")],
        empty_tools(),
        {"task_center": {"disk_space_safety_mb": 0}},
        executor=executor,
        task_repository=repository,
        history_root=tmp_path / "history",
        history_writer=lambda root, records: None,
    )

    runner.run()

    assert [job.source.name for job in executor.calls] == ["new.docx"]
    assert [task.task_id for task in repository.load()] == ["recovered"]
