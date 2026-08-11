from __future__ import annotations

import json

from ai_material_preprocessor.services.updates import (
    UpdateState,
    check_for_updates,
)


def test_update_check_never_opens_network_when_disabled() -> None:
    def forbidden_open(_request, timeout: float):
        raise AssertionError(f"network opened with timeout={timeout}")

    result = check_for_updates(
        current_version="2.0.0rc1",
        enabled=False,
        opener=forbidden_open,
    )

    assert result.state is UpdateState.DISABLED
    assert "设置" in result.message


def test_update_check_selects_newest_non_draft_release() -> None:
    payload = [
        {
            "tag_name": "v2.0.0rc2",
            "html_url": "https://example.invalid/rc2",
            "name": "2.0 RC2",
            "draft": False,
        },
        {
            "tag_name": "v9.0.0",
            "html_url": "https://example.invalid/draft",
            "name": "draft",
            "draft": True,
        },
    ]

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

    result = check_for_updates(
        current_version="2.0.0rc1",
        enabled=True,
        opener=lambda _request, timeout: Response(),
    )

    assert result.state is UpdateState.AVAILABLE
    assert result.latest_version == "2.0.0rc2"
    assert result.release_url == "https://example.invalid/rc2"


def test_update_check_returns_readable_error_without_leaking_response_content() -> None:
    def failed_open(_request, timeout: float):
        raise OSError("private proxy detail")

    result = check_for_updates(
        current_version="2.0.0rc1",
        enabled=True,
        opener=failed_open,
    )

    assert result.state is UpdateState.ERROR
    assert "稍后" in result.message
    assert "private proxy detail" not in result.message
