import json
from datetime import UTC, datetime
from pathlib import Path

from ai_material_preprocessor.models import Operation
from ai_material_preprocessor.services.task_manifest import (
    TaskRecord,
    clear_history,
    default_history_root,
    history_usage,
    write_task_manifest,
)


def test_task_manifest_records_success_failure_sizes_and_absolute_outputs(tmp_path: Path) -> None:
    root = tmp_path / "outputs"
    output = root / "AI资料包" / "lesson" / "content.md"
    output.parent.mkdir(parents=True)
    output.write_text("content", encoding="utf-8")
    source = tmp_path / "lesson.docx"
    source.write_bytes(b"source")
    records = [
        TaskRecord(source, Operation.TO_MARKDOWN, "success", output=output),
        TaskRecord(tmp_path / "broken.pdf", Operation.TO_MARKDOWN, "failed", error="bad pdf"),
    ]

    manifest = write_task_manifest(
        root,
        records,
        created_at=datetime(2026, 8, 1, 2, 3, 4, tzinfo=UTC),
        task_id="task-test",
    )

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest.name == "manifest.json"
    assert payload["task_id"] == "task-test"
    assert payload["summary"] == {"total": 2, "success": 1, "failed": 1}
    assert payload["items"][0]["output"] == str(output.resolve())
    assert payload["items"][0]["source_size"] == 6
    assert payload["items"][0]["output_size"] == 7
    assert payload["items"][1]["error"] == "bad pdf"


def test_default_history_root_uses_local_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert default_history_root() == tmp_path / "AI Material Preprocessor" / "History"


def test_manifest_is_kept_under_central_history_not_export_folder(tmp_path: Path) -> None:
    export_root = tmp_path / "exports"
    history_root = tmp_path / "app-history"
    output = export_root / "lesson.pdf"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"pdf")
    source = tmp_path / "lesson.docx"
    source.write_bytes(b"docx")

    manifest = write_task_manifest(
        history_root,
        [TaskRecord(source, Operation.TO_PDF, "success", output=output)],
        created_at=datetime(2026, 8, 1, 2, 3, 4, tzinfo=UTC),
        task_id="task-central",
    )

    assert manifest.is_relative_to(history_root)
    assert not (export_root / "任务记录").exists()


def test_history_usage_and_clear_only_affect_history_root(tmp_path: Path) -> None:
    history = tmp_path / "History"
    first = history / "2026" / "08" / "task-a" / "manifest.json"
    second = history / "2026" / "09" / "task-b" / "manifest.json"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_bytes(b"1234")
    second.write_bytes(b"123456")
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")

    usage = history_usage(history)
    removed = clear_history(history)

    assert usage.task_count == 2
    assert usage.total_bytes == 10
    assert removed == usage
    assert not history.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
