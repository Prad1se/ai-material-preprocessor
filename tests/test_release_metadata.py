from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ai_material_preprocessor.services.release_metadata import validate_release_metadata

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = PROJECT_ROOT / "scripts" / "check_release_metadata.py"


def _write_project(
    root: Path,
    *,
    version: str = "2.0.0rc1",
    readme_zh: str | None = "<!-- release-version: 2.0.0rc1 -->",
    readme_en: str | None = "<!-- release-version: 2.0.0rc1 -->",
    changelog: str = "## [2.0.0rc1] - fixture",
    package_version: str | None = None,
) -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "fixture"\nversion = "{version}"\n', encoding="utf-8"
    )
    package_dir = root / "src" / "ai_material_preprocessor"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text(
        f'__version__ = "{package_version or version}"\n', encoding="utf-8"
    )
    if readme_zh is not None:
        (root / "README.md").write_text(readme_zh, encoding="utf-8")
    if readme_en is not None:
        (root / "README.en.md").write_text(readme_en, encoding="utf-8")
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")


def test_marker_readmes_pass_when_versions_are_consistent(tmp_path: Path) -> None:
    _write_project(tmp_path)

    result = validate_release_metadata(tmp_path)

    assert result.version == "2.0.0rc1"
    assert result.errors == ()


def test_english_readme_with_marker_passes(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        readme_zh="说明：当前稳定版本 2.0.0rc1。\n\n<!-- release-version: 2.0.0rc1 -->",
        readme_en="Status: current stable release.\n\n<!-- release-version: 2.0.0rc1 -->",
    )

    result = validate_release_metadata(tmp_path)

    assert result.errors == ()


def test_legacy_chinese_format_still_parses(tmp_path: Path) -> None:
    _write_project(tmp_path, readme_zh="当前版本：**2.0.0rc1**")

    result = validate_release_metadata(tmp_path)

    assert result.errors == ()


def test_english_readme_is_optional_for_legacy_checkouts(tmp_path: Path) -> None:
    _write_project(tmp_path, readme_en=None)

    result = validate_release_metadata(tmp_path)

    assert result.errors == ()


def test_chinese_english_version_mismatch_is_detected(tmp_path: Path) -> None:
    _write_project(tmp_path, readme_en="<!-- release-version: 2.0.0 -->")

    result = validate_release_metadata(tmp_path)

    assert "Chinese and English README versions differ: 2.0.0rc1 != 2.0.0" in result.errors


def test_readme_version_mismatch_with_pyproject_is_detected(tmp_path: Path) -> None:
    _write_project(tmp_path, version="2.0.0rc1", readme_zh="<!-- release-version: 2.0.0 -->")
    (tmp_path / "README.en.md").write_text("<!-- release-version: 2.0.0 -->", encoding="utf-8")

    result = validate_release_metadata(tmp_path)

    assert "README (Chinese) version 2.0.0 does not match 2.0.0rc1" in result.errors
    assert "README (English) version 2.0.0 does not match 2.0.0rc1" in result.errors


def test_missing_marker_without_legacy_is_reported(tmp_path: Path) -> None:
    _write_project(tmp_path, readme_zh="# Title\n\nWelcome to the tool.")

    result = validate_release_metadata(tmp_path)

    assert "Chinese README does not declare a release version" in result.errors


def test_malformed_marker_is_reported(tmp_path: Path) -> None:
    _write_project(tmp_path, readme_zh="<!-- release-version: v2.0.0rc1 -->")

    result = validate_release_metadata(tmp_path)

    assert any("release-version marker has an invalid format" in error for error in result.errors)


def test_empty_marker_value_is_reported(tmp_path: Path) -> None:
    _write_project(tmp_path, readme_zh="<!-- release-version: -->")

    result = validate_release_metadata(tmp_path)

    assert "Chinese README release-version marker is missing a version value" in result.errors


def test_changelog_version_mismatch_is_detected(tmp_path: Path) -> None:
    _write_project(tmp_path, changelog="## [2.0.0] - fixture")

    result = validate_release_metadata(tmp_path)

    assert "changelog version 2.0.0 does not match 2.0.0rc1" in result.errors


def test_cli_accepts_expected_version(tmp_path: Path) -> None:
    _write_project(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--project-root",
            str(tmp_path),
            "--expected-version",
            "2.0.0rc1",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["version"] == "2.0.0rc1"
    assert payload["errors"] == []


def test_cli_rejects_mismatched_expected_version(tmp_path: Path) -> None:
    _write_project(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--project-root",
            str(tmp_path),
            "--expected-version",
            "9.9.9",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert "expected version 9.9.9, project declares 2.0.0rc1" in payload["errors"]
