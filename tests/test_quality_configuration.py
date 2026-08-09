import tomllib
from pathlib import Path


def test_mypy_skips_deep_analysis_of_runtime_adapter_dependencies() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    overrides = config["tool"]["mypy"].get("overrides", [])
    skipped_modules = {
        module
        for override in overrides
        if override.get("follow_imports") == "skip"
        for module in override.get("module", [])
    }

    assert {
        "markitdown",
        "markitdown.*",
        "onnxruntime",
        "onnxruntime.*",
        "pypdfium2",
        "pypdfium2.*",
        "rapidocr",
        "rapidocr.*",
    } <= skipped_modules
