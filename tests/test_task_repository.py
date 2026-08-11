from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ai_material_preprocessor.models import Job, Operation, QueuedTask, TaskStatus
from ai_material_preprocessor.services.task_repository import PersistentTaskQueue


def _task(tmp_path: Path, *, status: TaskStatus = TaskStatus.WAITING) -> QueuedTask:
    now = datetime(2026, 8, 10, 9, 30, tzinfo=UTC)
    return QueuedTask(
        task_id="task-中文-path",
        job=Job(
            tmp_path / "课程 资料.docx",
            Operation.TO_MARKDOWN,
            tmp_path / "输出 目录",
            project="毕业项目",
        ),
        status=status,
        progress=35 if status is TaskStatus.RUNNING else 0,
        attempts=1 if status is TaskStatus.RUNNING else 0,
        created_at=now,
        updated_at=now,
    )


def test_persistent_task_queue_round_trips_typed_jobs_and_unicode_paths(
    tmp_path: Path,
) -> None:
    repository = PersistentTaskQueue(tmp_path / "state" / "tasks.json")
    expected = _task(tmp_path)

    repository.save([expected])
    loaded = repository.load()

    assert loaded == [expected]
    assert json.loads(repository.path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert not repository.path.with_suffix(".json.tmp").exists()


def test_loading_after_abnormal_exit_marks_only_running_tasks_interrupted(
    tmp_path: Path,
) -> None:
    repository = PersistentTaskQueue(tmp_path / "tasks.json")
    waiting = _task(tmp_path)
    running = _task(tmp_path, status=TaskStatus.RUNNING).with_changes(task_id="running")
    repository.save([waiting, running])

    recovered = repository.load(recover_interrupted=True)

    assert [task.status for task in recovered] == [
        TaskStatus.WAITING,
        TaskStatus.INTERRUPTED,
    ]
    assert recovered[1].error == "应用在任务运行期间退出；可以安全重试。"
    assert repository.load()[1].status is TaskStatus.INTERRUPTED


def test_corrupt_queue_is_quarantined_and_does_not_block_startup(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    path.write_text("not-json", encoding="utf-8")
    repository = PersistentTaskQueue(path)

    assert repository.load() == []
    assert not path.exists()
    assert list(tmp_path.glob("tasks.corrupt-*.json"))
