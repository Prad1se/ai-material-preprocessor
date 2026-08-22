from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_ROOT = PROJECT_ROOT / "examples"

_PRIVATE_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\/]|/Users/|\\Users\\|/tmp/|%TEMP%|%LOCALAPPDATA%|"
    r"%USERPROFILE%|C:\\Users)",
    flags=re.IGNORECASE,
)


def test_examples_directory_has_both_demo_examples() -> None:
    for name in ("research-paper", "course-material"):
        example = EXAMPLES_ROOT / name
        assert example.is_dir(), f"missing example: {name}"
        assert (example / "README.md").is_file()
        assert (example / "input").is_dir()
        assert (example / "sample-context-pack" / "manifest.json").is_file()


def test_example_packs_are_real_context_packs() -> None:
    for name in ("research-paper", "course-material"):
        manifest = (EXAMPLES_ROOT / name / "sample-context-pack" / "manifest.json").read_text(
            encoding="utf-8"
        )
        import json

        payload = json.loads(manifest)
        assert payload["package_type"] == "ai_context_pack"
        assert payload["context_pack_version"] == 1
        assert (EXAMPLES_ROOT / name / "sample-context-pack" / "START_HERE.md").is_file()
        assert (EXAMPLES_ROOT / name / "sample-context-pack" / "content.md").is_file()
        assert (EXAMPLES_ROOT / name / "sample-context-pack" / "context-report.json").is_file()
        assert (EXAMPLES_ROOT / name / "sample-context-pack" / "packs" / "001-context.md").is_file()


def test_examples_contain_no_private_paths() -> None:
    if not EXAMPLES_ROOT.is_dir():
        pytest.skip("examples/ not present")
    scanned = 0
    for path in EXAMPLES_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".json", ".txt"}:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        assert not _PRIVATE_PATH_PATTERN.search(text), f"private path found in {path}"
    assert scanned >= 10


def test_example_inputs_are_small_synthetic_files() -> None:
    pdf = EXAMPLES_ROOT / "research-paper" / "input" / "sample-paper.pdf"
    docx = EXAMPLES_ROOT / "course-material" / "input" / "sample-lecture.docx"
    assert pdf.is_file() and pdf.stat().st_size < 20_000
    assert docx.is_file() and docx.stat().st_size < 20_000
