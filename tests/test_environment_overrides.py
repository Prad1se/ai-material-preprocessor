from pathlib import Path

from ai_material_preprocessor.services.environment import detect_tools


def test_markitdown_custom_path_precedes_installed_python_package(tmp_path: Path) -> None:
    executable = tmp_path / "工具 目录" / "markitdown.exe"
    executable.parent.mkdir()
    executable.touch()

    result = detect_tools({"tools": {"markitdown": str(executable)}})

    assert result["markitdown"].path == str(executable)
    assert result["markitdown"].source == "配置"
