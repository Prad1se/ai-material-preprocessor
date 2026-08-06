from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .. import __version__
from ..models import Operation


@dataclass(frozen=True)
class TaskRecord:
    source: Path
    operation: Operation
    status: str
    output: Path | None = None
    error: str = ""


@dataclass(frozen=True)
class HistoryUsage:
    task_count: int
    total_bytes: int


def default_history_root() -> Path:
    """Return one stable, user-local location for all processing history."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / "AppData" / "Local"
    return base / "AI Material Preprocessor" / "History"


def resolve_history_root(config: dict | None = None) -> Path:
    configured = str((config or {}).get("history_directory", "")).strip()
    return Path(os.path.expandvars(configured)).expanduser().resolve() if configured else default_history_root()


def history_usage(history_root: Path) -> HistoryUsage:
    if not history_root.is_dir():
        return HistoryUsage(0, 0)
    manifests = list(history_root.rglob("manifest.json"))
    total = 0
    for path in history_root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return HistoryUsage(len(manifests), total)


def clear_history(history_root: Path) -> HistoryUsage:
    """Permanently remove only the resolved history directory."""
    root = history_root.resolve()
    if root == root.parent or root == Path.home().resolve() or len(root.parts) < 3:
        raise ValueError("拒绝清理过于宽泛的目录。")
    usage = history_usage(root)
    if root.exists():
        shutil.rmtree(root)
    return usage


def _size(path: Path | None) -> int | None:
    try:
        return path.stat().st_size if path and path.is_file() else None
    except OSError:
        return None


def write_task_manifest(
    history_root: Path,
    records: list[TaskRecord],
    *,
    created_at: datetime | None = None,
    task_id: str | None = None,
) -> Path:
    created = created_at or datetime.now().astimezone()
    identifier = task_id or f"task-{uuid.uuid4().hex[:12]}"
    task_folder = (
        history_root
        / created.strftime("%Y")
        / created.strftime("%m")
        / f"{created.strftime('%Y%m%d-%H%M%S')}-{identifier}"
    )
    base = task_folder
    counter = 2
    while task_folder.exists():
        task_folder = base.with_name(f"{base.name}-{counter}")
        counter += 1
    task_folder.mkdir(parents=True)
    success = sum(record.status == "success" for record in records)
    failed = sum(record.status == "failed" for record in records)
    payload = {
        "manifest_type": "processing_task",
        "schema_version": 1,
        "application_version": __version__,
        "task_id": identifier,
        "created_at": created.isoformat(timespec="seconds"),
        "summary": {"total": len(records), "success": success, "failed": failed},
        "items": [
            {
                "source": str(record.source.resolve()),
                "source_size": _size(record.source),
                "operation": record.operation.name,
                "operation_label": record.operation.value,
                "status": record.status,
                "output": str(record.output.resolve()) if record.output else None,
                "output_size": _size(record.output),
                "error": record.error or None,
            }
            for record in records
        ],
    }
    manifest = task_folder / "manifest.json"
    manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
