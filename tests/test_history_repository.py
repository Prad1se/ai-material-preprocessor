from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai_material_preprocessor.models import Operation, TaskStatus
from ai_material_preprocessor.services.history_repository import HistoryRepository
from ai_material_preprocessor.services.task_manifest import TaskRecord, write_task_manifest


def _record(
    root: Path,
    *,
    task_id: str,
    created_at: datetime,
    source_name: str,
    operation: Operation,
    status: TaskStatus,
    cache: Path | None = None,
) -> tuple[Path, Path, Path]:
    source = root.parent / "sources" / source_name
    output = root.parent / "outputs" / f"{Path(source_name).stem}.result"
    source.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("original", encoding="utf-8")
    output.write_text("result", encoding="utf-8")
    manifest = write_task_manifest(
        root,
        [
            TaskRecord(
                source,
                operation,
                status,
                output=output if status is TaskStatus.SUCCESS else None,
                error="failed" if status is TaskStatus.FAILED else "",
                cache_paths=(cache,) if cache else (),
            )
        ],
        created_at=created_at,
        task_id=task_id,
    )
    return manifest, source, output


def test_history_search_and_filters_use_manifest_metadata(tmp_path: Path) -> None:
    history = tmp_path / "History"
    now = datetime(2026, 8, 10, tzinfo=UTC)
    _record(
        history,
        task_id="doc",
        created_at=now,
        source_name="课程 资料.docx",
        operation=Operation.TO_MARKDOWN,
        status=TaskStatus.SUCCESS,
    )
    _record(
        history,
        task_id="video",
        created_at=now + timedelta(minutes=1),
        source_name="broken-video.mp4",
        operation=Operation.COMPRESS_VIDEO,
        status=TaskStatus.FAILED,
    )
    repository = HistoryRepository(history)

    assert [entry.task_id for entry in repository.search(query="课程")] == ["doc"]
    assert [entry.task_id for entry in repository.search(status=TaskStatus.FAILED)] == ["video"]
    assert [entry.task_id for entry in repository.search(operation=Operation.TO_MARKDOWN)] == [
        "doc"
    ]


def test_deleting_selected_history_never_deletes_sources_outputs_or_other_records(
    tmp_path: Path,
) -> None:
    history = tmp_path / "History"
    now = datetime(2026, 8, 10, tzinfo=UTC)
    first_manifest, first_source, first_output = _record(
        history,
        task_id="first",
        created_at=now,
        source_name="first.docx",
        operation=Operation.TO_PDF,
        status=TaskStatus.SUCCESS,
    )
    second_manifest, second_source, second_output = _record(
        history,
        task_id="second",
        created_at=now + timedelta(seconds=1),
        source_name="second.docx",
        operation=Operation.TO_PDF,
        status=TaskStatus.SUCCESS,
    )
    repository = HistoryRepository(history)

    removed = repository.delete_records(["first"])

    assert removed == 1
    assert not first_manifest.exists()
    assert second_manifest.exists()
    assert first_source.exists() and first_output.exists()
    assert second_source.exists() and second_output.exists()


def test_cache_deletion_is_separate_and_scoped_to_application_cache(tmp_path: Path) -> None:
    history = tmp_path / "History"
    cache_root = tmp_path / "Cache"
    cache = cache_root / "task-one" / "preview.png"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"preview")
    outside = tmp_path / "do-not-delete.txt"
    outside.write_text("keep", encoding="utf-8")
    now = datetime(2026, 8, 10, tzinfo=UTC)
    manifest, source, output = _record(
        history,
        task_id="one",
        created_at=now,
        source_name="one.docx",
        operation=Operation.TO_MARKDOWN,
        status=TaskStatus.SUCCESS,
        cache=cache,
    )
    repository = HistoryRepository(history, cache_root=cache_root)

    removed = repository.delete_caches(["one"])

    assert removed == 1
    assert not cache.exists()
    assert manifest.exists() and source.exists() and output.exists()
    assert outside.read_text(encoding="utf-8") == "keep"


def test_automatic_cleanup_applies_retention_then_size_limit_oldest_first(
    tmp_path: Path,
) -> None:
    history = tmp_path / "History"
    now = datetime(2026, 8, 10, tzinfo=UTC)
    old_manifest, old_source, old_output = _record(
        history,
        task_id="expired",
        created_at=now - timedelta(days=100),
        source_name="expired.docx",
        operation=Operation.TO_MARKDOWN,
        status=TaskStatus.SUCCESS,
    )
    middle_manifest, middle_source, middle_output = _record(
        history,
        task_id="middle",
        created_at=now - timedelta(days=2),
        source_name="middle.docx",
        operation=Operation.TO_MARKDOWN,
        status=TaskStatus.SUCCESS,
    )
    newest_manifest, newest_source, newest_output = _record(
        history,
        task_id="newest",
        created_at=now - timedelta(days=1),
        source_name="newest.docx",
        operation=Operation.TO_MARKDOWN,
        status=TaskStatus.SUCCESS,
    )
    middle_manifest.parent.joinpath("padding.bin").write_bytes(b"x" * 1000)
    newest_manifest.parent.joinpath("padding.bin").write_bytes(b"x" * 1000)
    repository = HistoryRepository(history)
    newest_size = sum(
        path.stat().st_size for path in newest_manifest.parent.rglob("*") if path.is_file()
    )

    result = repository.cleanup(
        retention_days=30,
        max_bytes=newest_size + 10,
        now=now,
    )

    assert result.expired_records == 1
    assert result.size_limited_records == 1
    assert not old_manifest.exists() and not middle_manifest.exists()
    assert newest_manifest.exists()
    for path in (
        old_source,
        old_output,
        middle_source,
        middle_output,
        newest_source,
        newest_output,
    ):
        assert path.exists()
