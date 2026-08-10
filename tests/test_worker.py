from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ai_material_preprocessor.errors import ErrorCode, UserFacingError
from ai_material_preprocessor.infrastructure.processes import CancellationToken
from ai_material_preprocessor.models import Job, Operation, QueuedTask, TaskStatus, ToolStatus
from ai_material_preprocessor.services.job_executor import TaskExecutionResult
from ai_material_preprocessor.services.task_repository import PersistentTaskQueue
from ai_material_preprocessor.ui.workers import Worker


class FakeExecutor:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def execute_one(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress=None,
    ) -> TaskExecutionResult:
        self.calls += 1
        if on_progress:
            on_progress(50, "处理中")
        if self.fail:
            raise UserFacingError(
                ErrorCode.CONVERSION_FAILED,
                "文档转换失败，请检查文件。",
                technical_detail=str(job.source),
                retryable=True,
            )
        return TaskExecutionResult(job.output_root / "lesson.md", ({"score": 100},))


class FailingPreflight:
    def check(self, jobs, *, safety_margin_bytes):
        raise UserFacingError(ErrorCode.FILE_SYSTEM, "输出目录空间不足。", retryable=True)


def empty_tools() -> dict[str, ToolStatus]:
    return {
        name: ToolStatus(name, None)
        for name in (
            "markitdown",
            "ffmpeg",
            "ffprobe",
            "exiftool",
            "libreoffice",
            "winword",
            "powerpoint",
            "rapidocr",
        )
    }


def test_worker_adapts_task_center_updates_to_qt_signals(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.write_bytes(b"docx")
    job = Job(source, Operation.TO_MARKDOWN, tmp_path / "out")
    written = []
    worker = Worker(
        [job],
        empty_tools(),
        {"task_center": {"disk_space_safety_mb": 0}},
        executor=FakeExecutor(),
        task_repository=PersistentTaskQueue(tmp_path / "state.json"),
        history_root=tmp_path / "history",
        history_writer=lambda root, records: written.append((root, records)),
    )
    completed: list[tuple[list[str], list[str], list[dict]]] = []
    updates: list[tuple[str, str, int, str]] = []
    progress: list[tuple[int, str]] = []
    worker.completed.connect(
        lambda outputs, errors, reports: completed.append((outputs, errors, reports))
    )
    worker.task_changed.connect(
        lambda task_id, status, value, message: updates.append((task_id, status, value, message))
    )
    worker.progress.connect(lambda value, message: progress.append((value, message)))

    worker.run()

    assert completed == [([str(tmp_path / "out" / "lesson.md")], [], [{"score": 100}])]
    assert any(
        status == TaskStatus.RUNNING.value and value == 50 for _, status, value, _ in updates
    )
    assert updates[-1][1:3] == (TaskStatus.SUCCESS.value, 100)
    assert progress[-1][0] == 100
    assert len(written) == 1
    assert written[0][1][0].status is TaskStatus.SUCCESS
    assert written[0][1][0].quality_summary == {
        "score": 100,
        "chunk_count": 0,
        "ocr_pages": [],
        "issues": [],
    }
    assert worker.task_repository.load() == []


def test_worker_exposes_safe_failure_message_not_private_detail(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "private.docx"
    source.write_bytes(b"docx")
    worker = Worker(
        [Job(source, Operation.TO_MARKDOWN, tmp_path / "out")],
        empty_tools(),
        {"task_center": {"disk_space_safety_mb": 0}},
        executor=FakeExecutor(fail=True),
        task_repository=PersistentTaskQueue(tmp_path / "state.json"),
        history_root=tmp_path / "history",
        history_writer=lambda root, records: None,
    )
    completed: list[tuple[list[str], list[str], list[dict]]] = []
    worker.completed.connect(
        lambda outputs, errors, reports: completed.append((outputs, errors, reports))
    )

    worker.run()

    assert completed[0][1] == ["private.docx：文档转换失败，请检查文件。"]
    assert str(source) not in completed[0][1][0]


def test_worker_checks_disk_space_before_calling_executor(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "large.mp4"
    source.write_bytes(b"video")
    executor = FakeExecutor()
    worker = Worker(
        [Job(source, Operation.STANDARDIZE_MP4, tmp_path / "out")],
        empty_tools(),
        {"task_center": {"disk_space_safety_mb": 512}},
        executor=executor,
        task_repository=PersistentTaskQueue(tmp_path / "state.json"),
        disk_preflight=FailingPreflight(),
        history_root=tmp_path / "history",
        history_writer=lambda root, records: None,
    )
    failures: list[str] = []
    worker.failed.connect(failures.append)

    worker.run()

    assert executor.calls == 0
    assert failures == ["输出目录空间不足。"]
    assert worker.tasks[0].status is TaskStatus.WAITING


def test_worker_can_cancel_waiting_item_by_task_id(qtbot, tmp_path: Path) -> None:
    jobs = []
    for name in ("one.docx", "two.docx"):
        source = tmp_path / name
        source.write_bytes(b"docx")
        jobs.append(Job(source, Operation.TO_MARKDOWN, tmp_path / "out"))
    executor = FakeExecutor()
    worker = Worker(
        jobs,
        empty_tools(),
        {"task_center": {"disk_space_safety_mb": 0}},
        executor=executor,
        task_repository=PersistentTaskQueue(tmp_path / "state.json"),
        history_root=tmp_path / "history",
        history_writer=lambda root, records: None,
    )

    assert worker.cancel_task(worker.tasks[1].task_id)
    worker.run()

    assert executor.calls == 1
    assert worker.tasks[1].status is TaskStatus.CANCELLED


def test_new_batch_does_not_run_recovered_task_until_user_selects_retry(
    qtbot, tmp_path: Path
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
    worker = Worker(
        [Job(new_source, Operation.TO_MARKDOWN, tmp_path / "out")],
        empty_tools(),
        {"task_center": {"disk_space_safety_mb": 0}},
        executor=executor,
        task_repository=repository,
        history_root=tmp_path / "history",
        history_writer=lambda root, records: None,
    )

    worker.run()

    assert executor.calls == 1
    saved = repository.load()
    assert len(saved) == 1
    assert saved[0].task_id == "recovered"
    assert saved[0].status is TaskStatus.WAITING
