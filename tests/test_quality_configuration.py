import tomllib
from pathlib import Path


def test_mypy_does_not_analyze_third_party_site_packages() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert config["tool"]["mypy"]["no_site_packages"] is True
