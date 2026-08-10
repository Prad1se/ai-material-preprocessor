from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_public_fixture_catalog_contains_document_and_metadata_cases() -> None:
    markdown = FIXTURES / "markdown" / "complex-source.md"
    exiftool = FIXTURES / "metadata" / "exiftool-video.json"
    ffprobe = FIXTURES / "metadata" / "ffprobe-video.json"

    assert markdown.is_file()
    assert "<!-- Page: 1 -->" in markdown.read_text(encoding="utf-8")
    assert json.loads(exiftool.read_text(encoding="utf-8"))[0]["City"] == "杭州"
    assert json.loads(ffprobe.read_text(encoding="utf-8"))["streams"][0]["codec_name"] == "h264"


def test_text_fixtures_contain_no_private_windows_profile_paths() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in FIXTURES.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".html", ".json", ".txt"}
    ).lower()

    assert "c:\\users\\" not in text
    assert "pradise" not in text
