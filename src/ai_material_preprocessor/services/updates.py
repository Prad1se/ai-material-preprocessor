from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

RELEASES_API = "https://api.github.com/repos/Prad1se/ai-material-preprocessor/releases?per_page=10"


class UpdateState(StrEnum):
    DISABLED = "disabled"
    UP_TO_DATE = "up_to_date"
    AVAILABLE = "available"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class UpdateCheckResult:
    state: UpdateState
    message: str
    latest_version: str = ""
    release_url: str = ""


def _release_version(raw: object) -> Version | None:
    if not isinstance(raw, str):
        return None
    try:
        return Version(raw.removeprefix("v"))
    except InvalidVersion:
        return None


def _newest_release(payload: object, current: Version) -> dict[str, Any] | None:
    if not isinstance(payload, list):
        return None
    candidates: list[tuple[Version, dict[str, Any]]] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("draft") is True:
            continue
        version = _release_version(item.get("tag_name"))
        if version is not None and version > current:
            candidates.append((version, item))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def check_for_updates(
    *,
    current_version: str,
    enabled: bool,
    opener=urlopen,
    timeout: float = 8.0,
) -> UpdateCheckResult:
    """Check GitHub only after the user explicitly enabled network access."""

    if not enabled:
        return UpdateCheckResult(UpdateState.DISABLED, "请先在设置中允许联网检查更新。")
    try:
        current = Version(current_version)
        request = Request(
            RELEASES_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"AI-Material-Preprocessor/{current_version}",
            },
        )
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        release = _newest_release(payload, current)
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return UpdateCheckResult(UpdateState.ERROR, "暂时无法检查更新，请稍后重试。")

    if release is None:
        return UpdateCheckResult(UpdateState.UP_TO_DATE, "当前已经是可用的最新版本。")
    version = str(_release_version(release.get("tag_name")))
    return UpdateCheckResult(
        UpdateState.AVAILABLE,
        f"发现新版本 {version}。",
        latest_version=version,
        release_url=str(release.get("html_url") or ""),
    )
