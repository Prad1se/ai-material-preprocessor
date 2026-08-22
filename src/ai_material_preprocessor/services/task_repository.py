from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from ..models import Job, Operation, QueuedTask, TaskStatus


def default_task_state_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "AI Material Preprocessor" / "State"


def resolve_task_queue_path(config: dict | None = None) -> Path:
    task_config = (config or {}).get("task_center", {})
    configured = str(task_config.get("state_directory", "")).strip()
    root = (
        Path(os.path.expandvars(configured)).expanduser().resolve()
        if configured
        else default_task_state_root()
    )
    return root / "task-queue.json"


class PersistentTaskQueue:
    """Atomic JSON persistence for recoverable task-center state."""

    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def _serialize(task: QueuedTask) -> dict[str, object]:
        return {
            "task_id": task.task_id,
            "source": str(task.job.source),
            "operation": task.job.operation.name,
            "output_root": str(task.job.output_root),
            "sources": [str(path) for path in task.job.sources],
            "context_budget": task.job.context_budget,
            "context_ocr_enabled": task.job.context_ocr_enabled,
            "location": task.job.location,
            "project": task.job.project,
            "status": task.status.value,
            "progress": task.progress,
            "attempts": task.attempts,
            "error": task.error,
            "output": str(task.output) if task.output else None,
            "message": task.message,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        }

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _parse_int(value: object, default: int = 0) -> int:
        if isinstance(value, (int, str)):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    @staticmethod
    def _parse_optional_bool(value: object) -> bool | None:
        if value is None or isinstance(value, bool):
            return value
        raise TypeError("invalid optional boolean")

    @classmethod
    def _deserialize(cls, payload: dict[str, object]) -> QueuedTask:
        raw_sources = payload.get("sources", [])
        if not isinstance(raw_sources, list):
            raise TypeError("invalid task sources")
        return QueuedTask(
            task_id=str(payload["task_id"]),
            job=Job(
                source=Path(str(payload["source"])),
                operation=Operation[str(payload["operation"])],
                output_root=Path(str(payload["output_root"])),
                location=str(payload.get("location", "")),
                project=str(payload.get("project", "")),
                sources=tuple(Path(str(path)) for path in raw_sources),
                context_budget=(
                    cls._parse_int(payload["context_budget"])
                    if payload.get("context_budget") is not None
                    else None
                ),
                context_ocr_enabled=cls._parse_optional_bool(payload.get("context_ocr_enabled")),
            ),
            status=TaskStatus(str(payload.get("status", TaskStatus.WAITING.value))),
            progress=cls._parse_int(payload.get("progress", 0)),
            attempts=cls._parse_int(payload.get("attempts", 0)),
            error=str(payload.get("error", "")),
            output=Path(str(payload["output"])) if payload.get("output") else None,
            message=str(payload.get("message", "")),
            created_at=cls._parse_datetime(payload["created_at"]),
            updated_at=cls._parse_datetime(payload["updated_at"]),
            started_at=(
                cls._parse_datetime(payload["started_at"]) if payload.get("started_at") else None
            ),
            finished_at=(
                cls._parse_datetime(payload["finished_at"]) if payload.get("finished_at") else None
            ),
        )

    def save(self, tasks: list[QueuedTask]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "tasks": [self._serialize(task) for task in tasks],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def _quarantine_corrupt_file(self) -> None:
        if not self.path.exists():
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        quarantine = self.path.with_name(f"{self.path.stem}.corrupt-{stamp}{self.path.suffix}")
        os.replace(self.path, quarantine)

    def load(self, *, recover_interrupted: bool = False) -> list[QueuedTask]:
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("schema_version") != self.SCHEMA_VERSION:
                raise ValueError("unsupported task queue schema")
            items = raw.get("tasks", [])
            if not isinstance(items, list):
                raise ValueError("invalid task list")
            tasks = [self._deserialize(item) for item in items if isinstance(item, dict)]
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self._quarantine_corrupt_file()
            return []

        if recover_interrupted:
            now = datetime.now(UTC)
            recovered = [
                task.with_changes(
                    status=TaskStatus.INTERRUPTED,
                    progress=min(task.progress, 99),
                    error="应用在任务运行期间退出；可以安全重试。",
                    message="上次运行被中断",
                    updated_at=now,
                )
                if task.status is TaskStatus.RUNNING
                else task
                for task in tasks
            ]
            if recovered != tasks:
                self.save(recovered)
            tasks = recovered
        return tasks
