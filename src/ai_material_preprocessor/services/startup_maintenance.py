from __future__ import annotations

from typing import Protocol

from .config import coerce_int
from .history_repository import CleanupResult, HistoryRepository
from .task_manifest import resolve_history_root


class HistoryCleaner(Protocol):
    def cleanup(self, *, retention_days: int, max_bytes: int) -> CleanupResult | None: ...


def perform_startup_maintenance(
    config: dict,
    *,
    history_repository: HistoryCleaner | None = None,
) -> None:
    """Apply bounded history policies without touching inputs or outputs."""
    history_config = config.get("history", {})
    repository = history_repository or HistoryRepository(resolve_history_root(config))
    repository.cleanup(
        retention_days=coerce_int(
            history_config.get("retention_days"),
            90,
            minimum=0,
        ),
        max_bytes=coerce_int(
            history_config.get("max_size_mb"),
            512,
            minimum=0,
        )
        * 1024
        * 1024,
    )
