from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

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


def test_context_pack_job_sources_and_budget_round_trip(tmp_path: Path) -> None:
    repository = PersistentTaskQueue(tmp_path / "tasks.json")
    primary = tmp_path / "课程 资料.docx"
    secondary = tmp_path / "参考资料.pdf"
    expected = _task(tmp_path).with_changes(
        job=Job(
            primary,
            Operation.DOCUMENT_CONTEXT_PACK,
            tmp_path / "输出 目录",
            sources=(secondary,),
            context_budget=32_000,
            context_ocr_enabled=True,
        )
    )

    repository.save([expected])
    payload = json.loads(repository.path.read_text(encoding="utf-8"))
    loaded = repository.load()

    assert payload["schema_version"] == 1
    assert payload["tasks"][0]["sources"] == [str(secondary)]
    assert payload["tasks"][0]["context_budget"] == 32_000
    assert payload["tasks"][0]["context_ocr_enabled"] is True
    assert loaded == [expected]
    assert loaded[0].job.input_sources == (primary, secondary)


def test_job_accepts_a_full_source_tuple_when_primary_is_first(tmp_path: Path) -> None:
    primary = tmp_path / "primary.docx"
    secondary = tmp_path / "secondary.pdf"

    job = Job(
        primary,
        Operation.DOCUMENT_CONTEXT_PACK,
        tmp_path / "output",
        sources=(primary, secondary),
    )

    assert job.input_sources == (primary, secondary)


def test_job_rejects_invalid_context_budget_and_duplicate_primary_sources(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.docx"

    with pytest.raises(ValueError, match="positive"):
        Job(source, Operation.DOCUMENT_CONTEXT_PACK, tmp_path / "output", context_budget=0)
    with pytest.raises(ValueError, match="repeat|duplicate"):
        Job(
            source,
            Operation.DOCUMENT_CONTEXT_PACK,
            tmp_path / "output",
            sources=(tmp_path / "other.pdf", source),
        )


def test_legacy_task_payload_defaults_to_primary_source_and_no_budget(tmp_path: Path) -> None:
    repository = PersistentTaskQueue(tmp_path / "tasks.json")
    expected = _task(tmp_path)
    repository.save([expected])
    payload = json.loads(repository.path.read_text(encoding="utf-8"))
    payload["tasks"][0].pop("sources")
    payload["tasks"][0].pop("context_budget")
    payload["tasks"][0].pop("context_ocr_enabled")
    repository.path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = repository.load()

    assert loaded[0].job.sources == ()
    assert loaded[0].job.context_budget is None
    assert loaded[0].job.context_ocr_enabled is None
    assert loaded[0].job.input_sources == (expected.job.source,)


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


def test_v2_queue_operation_member_names_remain_compatible(tmp_path: Path) -> None:
    repository = PersistentTaskQueue(tmp_path / "tasks.json")
    expected_names = [operation.name for operation in Operation]
    tasks = [
        _task(tmp_path).with_changes(
            task_id=f"task-{index}",
            job=Job(
                tmp_path / f"source-{index}.dat",
                operation,
                tmp_path / "outputs",
            ),
        )
        for index, operation in enumerate(Operation, start=1)
    ]

    repository.save(tasks)
    payload = json.loads(repository.path.read_text(encoding="utf-8"))

    assert [item["operation"] for item in payload["tasks"]] == expected_names
    assert [task.job.operation for task in repository.load()] == list(Operation)
