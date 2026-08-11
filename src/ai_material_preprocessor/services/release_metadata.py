from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReleaseValidation:
    version: str
    errors: tuple[str, ...]


def _match_version(path: Path, pattern: str, label: str, errors: list[str]) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text)
    if match is None:
        errors.append(f"{label} does not declare a release version")
        return ""
    return match.group(1)


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
        "README": _match_version(
            project_root / "README.md",
            r"当前版本：\*\*([^*]+)\*\*",
            "README",
            errors,
        ),
        "changelog": _match_version(
            project_root / "CHANGELOG.md",
            r"## \[([^]]+)]",
            "CHANGELOG",
            errors,
        ),
    }
    for label, candidate in declared.items():
        if candidate and candidate != version:
            errors.append(f"{label} version {candidate} does not match {version}")
    return ReleaseValidation(version, tuple(errors))
