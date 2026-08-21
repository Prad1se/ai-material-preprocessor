from __future__ import annotations

from collections.abc import Set
from dataclasses import dataclass
from pathlib import Path

from ..services.input_discovery import discover_input_files
from .workspaces import WorkspaceId


@dataclass(frozen=True)
class WorkspaceInputSelection:
    accepted: tuple[Path, ...]
    foreign: tuple[Path, ...]
    foreign_workspace: WorkspaceId | None


def classify_workspace_inputs(
    paths: list[str],
    *,
    supported_extensions: Set[str],
    foreign_extensions: Set[str],
    foreign_workspace: WorkspaceId,
) -> WorkspaceInputSelection:
    discovered = discover_input_files(paths)
    accepted = tuple(path for path in discovered if path.suffix.lower() in supported_extensions)
    foreign = tuple(path for path in discovered if path.suffix.lower() in foreign_extensions)
    return WorkspaceInputSelection(
        accepted,
        foreign,
        foreign_workspace if foreign else None,
    )
