from __future__ import annotations

from pathlib import Path

from ai_material_preprocessor.errors import ErrorCode, UserFacingError
from ai_material_preprocessor.models import Job, Operation, TaskStatus, ToolStatus
from ai_material_preprocessor.services.job_executor import (
    BatchExecutionResult,
    TaskFailure,
)
from ai_material_preprocessor.services.task_manifest import TaskRecord
from ai_material_preprocessor.ui.workers import Worker


class FakeExecutor:
    def __init__(self, result: BatchExecutionResult) -> None:
        self.result = result

    def execute_batch(self, jobs, *, on_progress):
        on_progress(0, len(jobs), f"正在处理：{jobs[0].source.name}")
        on_progress(len(jobs), len(jobs), f"已处理：{jobs[-1].source.name}")
        return self.result


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


def test_worker_only_adapts_executor_result_to_qt_signals(qtbot, tmp_path: Path) -> None:
    job = Job(tmp_path / "lesson.docx", Operation.TO_MARKDOWN, tmp_path / "out")
    output = tmp_path / "out" / "lesson.md"
    record = TaskRecord(job.source, job.operation, TaskStatus.SUCCESS, output=output)
    result = BatchExecutionResult((output,), (), ({"score": 100},), (record,))
    written: list[tuple[Path, list[TaskRecord]]] = []
    worker = Worker(
        [job],
        empty_tools(),
        {},
        executor=FakeExecutor(result),
        history_root=tmp_path / "history",
        history_writer=lambda root, records: written.append((root, records)),
    )
    completed: list[tuple[list[str], list[str], list[dict]]] = []
    progress: list[tuple[int, str]] = []
    worker.completed.connect(
        lambda outputs, errors, reports: completed.append((outputs, errors, reports))
    )
    worker.progress.connect(lambda value, message: progress.append((value, message)))

    worker.run()

    assert completed == [([str(output)], [], [{"score": 100}])]
    assert progress[0][0] == 0 and progress[-1][0] == 100
    assert written == [(tmp_path / "history", [record])]


def test_worker_exposes_safe_failure_message_not_private_detail(qtbot, tmp_path: Path) -> None:
    job = Job(tmp_path / "private.docx", Operation.TO_MARKDOWN, tmp_path / "out")
    error = UserFacingError(
        ErrorCode.CONVERSION_FAILED,
        "文档转换失败，请检查文件。",
        technical_detail=str(job.source),
        retryable=True,
    )
    failure = TaskFailure(job.source, error)
    record = TaskRecord(job.source, job.operation, TaskStatus.FAILED, error=str(error))
    result = BatchExecutionResult((), (failure,), (), (record,))
    worker = Worker(
        [job],
        empty_tools(),
        {},
        executor=FakeExecutor(result),
        history_root=tmp_path / "history",
        history_writer=lambda root, records: None,
    )
    completed: list[tuple[list[str], list[str], list[dict]]] = []
    worker.completed.connect(
        lambda outputs, errors, reports: completed.append((outputs, errors, reports))
    )

    worker.run()

    assert completed[0][1] == ["private.docx：文档转换失败，请检查文件。"]
    assert str(job.source) not in completed[0][1][0]
