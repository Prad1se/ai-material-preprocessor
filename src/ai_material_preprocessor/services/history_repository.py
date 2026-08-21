from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..models import Operation, TaskStatus
from .task_manifest import history_usage


def default_cache_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "AI Material Preprocessor" / "Cache"


@dataclass(frozen=True)
class HistoryEntry:
    task_id: str
    created_at: datetime
    manifest_path: Path
    statuses: frozenset[TaskStatus]
    operations: frozenset[Operation]
    sources: tuple[Path, ...]
    outputs: tuple[Path, ...]
    cache_paths: tuple[Path, ...]
    quality_summaries: tuple[dict[str, object], ...]
    total_bytes: int


@dataclass(frozen=True)
class CleanupResult:
    expired_records: int = 0
    size_limited_records: int = 0


def _directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


class HistoryRepository:
    """Search and lifecycle operations for central history manifests only."""

    def __init__(self, root: Path, *, cache_root: Path | None = None) -> None:
        self.root = root.resolve()
        self.cache_root = cache_root.resolve() if cache_root else None

    @staticmethod
    def _parse_time(value: object) -> datetime:
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def _read(self, manifest: Path) -> HistoryEntry | None:
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            items = payload.get("items", [])
            statuses = frozenset(
                TaskStatus(str(item["status"])) for item in items if item.get("status")
            )
            operations = frozenset(
                Operation[str(item["operation"])] for item in items if item.get("operation")
            )
            sources = tuple(
                dict.fromkeys(
                    Path(str(source))
                    for item in items
                    for source in (
                        item.get("sources")
                        if isinstance(item.get("sources"), list) and item.get("sources")
                        else [item.get("source")]
                    )
                    if source
                )
            )
            outputs = tuple(Path(str(item["output"])) for item in items if item.get("output"))
            cache_paths = tuple(
                Path(str(cache)) for item in items for cache in item.get("cache_paths", []) if cache
            )
            quality_summaries = tuple(
                summary
                for item in items
                if isinstance((summary := item.get("quality_summary")), dict) and summary
            )
            return HistoryEntry(
                task_id=str(payload["task_id"]),
                created_at=self._parse_time(payload["created_at"]),
                manifest_path=manifest,
                statuses=statuses,
                operations=operations,
                sources=sources,
                outputs=outputs,
                cache_paths=cache_paths,
                quality_summaries=quality_summaries,
                total_bytes=_directory_size(manifest.parent),
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def all(self) -> list[HistoryEntry]:
        if not self.root.is_dir():
            return []
        entries = [self._read(path) for path in self.root.rglob("manifest.json")]
        return sorted(
            (entry for entry in entries if entry is not None),
            key=lambda entry: entry.created_at,
            reverse=True,
        )

    def details(self, task_id: str) -> dict | None:
        entry = next((item for item in self.all() if item.task_id == task_id), None)
        if entry is None:
            return None
        try:
            payload = json.loads(entry.manifest_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def search(
        self,
        *,
        query: str = "",
        status: TaskStatus | None = None,
        operation: Operation | None = None,
    ) -> list[HistoryEntry]:
        needle = query.casefold().strip()
        result: list[HistoryEntry] = []
        for entry in self.all():
            haystack = " ".join(
                [
                    entry.task_id,
                    *(path.name for path in entry.sources),
                    *(str(path) for path in entry.outputs),
                ]
            ).casefold()
            if needle and needle not in haystack:
                continue
            if status is not None and status not in entry.statuses:
                continue
            if operation is not None and operation not in entry.operations:
                continue
            result.append(entry)
        return result

    def _safe_record_folder(self, entry: HistoryEntry) -> Path | None:
        folder = entry.manifest_path.parent.resolve()
        if folder == self.root or not folder.is_relative_to(self.root):
            return None
        return folder

    def delete_records(self, task_ids: list[str]) -> int:
        selected = set(task_ids)
        removed = 0
        for entry in self.all():
            if entry.task_id not in selected:
                continue
            folder = self._safe_record_folder(entry)
            if folder and folder.is_dir():
                shutil.rmtree(folder)
                removed += 1
        return removed

    def delete_caches(self, task_ids: list[str]) -> int:
        if self.cache_root is None:
            return 0
        selected = set(task_ids)
        removed = 0
        for entry in self.all():
            if entry.task_id not in selected:
                continue
            for raw_path in entry.cache_paths:
                cache = raw_path.resolve()
                if cache == self.cache_root or not cache.is_relative_to(self.cache_root):
                    continue
                if cache.is_dir():
                    shutil.rmtree(cache)
                    removed += 1
                elif cache.is_file():
                    cache.unlink()
                    removed += 1
        return removed

    def cleanup(
        self,
        *,
        retention_days: int,
        max_bytes: int,
        now: datetime | None = None,
    ) -> CleanupResult:
        current = now or datetime.now(UTC)
        threshold = current - timedelta(days=max(0, retention_days))
        expired_ids = [
            entry.task_id
            for entry in self.all()
            if retention_days > 0 and entry.created_at < threshold
        ]
        expired = self.delete_records(expired_ids)
        limited = 0
        if max_bytes > 0:
            entries = sorted(self.all(), key=lambda entry: entry.created_at)
            total = history_usage(self.root).total_bytes
            for entry in entries:
                if total <= max_bytes:
                    break
                size = entry.total_bytes
                limited += self.delete_records([entry.task_id])
                total = max(0, total - size)
        return CleanupResult(expired, limited)
