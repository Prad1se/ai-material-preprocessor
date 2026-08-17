from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReleaseValidation:
    version: str
    errors: tuple[str, ...]


_RELEASE_VERSION_MARKER = re.compile(r"<!--\s*release-version\s*:\s*([^\s]+)\s*-->")
_RELEASE_VERSION_MARKER_PREFIX = re.compile(r"<!--\s*release-version")
_LEGACY_README_VERSION = re.compile(r"当前版本：\*\*([^*]+)\*\*")
_VERSION_SHAPE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+[0-9A-Za-z.\-]*")


def _match_version(path: Path, pattern: str, label: str, errors: list[str]) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text)
    if match is None:
        errors.append(f"{label} does not declare a release version")
        return ""
    return match.group(1)


def _readme_version(path: Path, label: str, errors: list[str]) -> str:
    """Read the release version declared in a README file.

    The machine-readable ``<!-- release-version: X -->`` marker is the stable
    contract so that natural-language copy can be rewritten freely. The
    historical Chinese ``当前版本：**X**`` expression remains a fallback.
    """
    text = path.read_text(encoding="utf-8")
    marker = _RELEASE_VERSION_MARKER.search(text)
    if marker is not None:
        candidate = marker.group(1)
        if _VERSION_SHAPE.fullmatch(candidate) is None:
            errors.append(f"{label} release-version marker has an invalid format: {candidate!r}")
            return ""
        return candidate
    if _RELEASE_VERSION_MARKER_PREFIX.search(text) is not None:
        errors.append(f"{label} release-version marker is missing a version value")
        return ""
    legacy = _LEGACY_README_VERSION.search(text)
    if legacy is not None:
        return legacy.group(1)
    errors.append(f"{label} does not declare a release version")
    return ""


def validate_release_metadata(project_root: Path) -> ReleaseValidation:
    errors: list[str] = []
    project = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    version = str(project["version"])
    declared = {
        "package": _match_version(
            project_root / "src" / "ai_material_preprocessor" / "__init__.py",
            r'__version__\s*=\s*"([^"]+)"',
            "package",
            errors,
        ),
        "changelog": _match_version(
            project_root / "CHANGELOG.md",
            r"## \[([^]]+)]",
            "CHANGELOG",
            errors,
        ),
    }
    readme_zh = _readme_version(project_root / "README.md", "Chinese README", errors)
    declared["README (Chinese)"] = readme_zh
    english_readme = project_root / "README.en.md"
    readme_en = (
        _readme_version(english_readme, "English README", errors)
        if english_readme.is_file()
        else ""
    )
    declared["README (English)"] = readme_en
    if readme_zh and readme_en and readme_zh != readme_en:
        errors.append(f"Chinese and English README versions differ: {readme_zh} != {readme_en}")
    for label, candidate in declared.items():
        if candidate and candidate != version:
            errors.append(f"{label} version {candidate} does not match {version}")
    return ReleaseValidation(version, tuple(errors))
