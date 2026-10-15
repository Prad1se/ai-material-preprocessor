"""Private, local-only diagnostics primitives.

Diagnostics are deliberately metadata-only: source paths, document contents,
command lines, and configuration values never belong in an event or export.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

_WINDOWS_PATH = re.compile(r"(?<![\w:])[A-Za-z]:[\\/][^\s\"']+")
_POSIX_PATH = re.compile(r"(?<![\w:])/(?:[^\s\"']+/)*[^\s\"']+")
_SAFE_DETAIL_KEYS = frozenset(
    {
        "available",
        "discovery_source",
        "error_code",
        "error_type",
        "operation",
        "overall",
        "source_suffix",
        "tool",
    }
)


def resolve_diagnostics_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return the app-owned local diagnostics directory, never a project path."""
    values = os.environ if environ is None else environ
    local_app_data = values.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / "AI Material Preprocessor" / "diagnostics"


def redact_text(value: object) -> str:
    """Remove absolute paths from a short diagnostic label."""
    text = str(value)
    text = _WINDOWS_PATH.sub("<redacted-path>", text)
    return _POSIX_PATH.sub("<redacted-path>", text)


def _safe_value(key: str, value: object) -> bool | float | int | str | None:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Path):
        return "<redacted-path>"
    return redact_text(value)[:160]


class DiagnosticLogger:
    """Append structured local events while never letting logging break work."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.root = root or resolve_diagnostics_root()
        self.clock = clock or (lambda: datetime.now().astimezone().isoformat(timespec="seconds"))

    def record(self, event: str, *, level: str = "info", **details: object) -> dict[str, object]:
        timestamp = self.clock()
        payload: dict[str, object] = {
            "schema_version": 1,
            "timestamp": timestamp,
            "level": level,
            "event": event,
        }
        payload.update(
            {
                key: _safe_value(key, value)
                for key, value in sorted(details.items())
                if key in _SAFE_DETAIL_KEYS
            }
        )
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            day = timestamp[:10]
            with (self.root / f"events-{day}.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            pass
        return payload

    def record_failure(
        self, event: str, error: BaseException, **details: object
    ) -> dict[str, object]:
        """Capture only the exception class, never exception text or traceback."""
        code = getattr(error, "code", None)
        if code is not None:
            details["error_code"] = getattr(code, "value", str(code))
        return self.record(event, level="error", error_type=type(error).__name__, **details)

    def recent_events(self, *, limit: int = 50) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        try:
            for path in sorted(self.root.glob("events-*.jsonl"), reverse=True):
                for line in reversed(path.read_text(encoding="utf-8").splitlines()):
                    payload = json.loads(line)
                    if isinstance(payload, dict):
                        events.append(payload)
                        if len(events) >= limit:
                            return events
        except (OSError, json.JSONDecodeError):
            return events
        return events
