from importlib.metadata import PackageNotFoundError

from ai_material_preprocessor.infrastructure.processes import CommandResult
from ai_material_preprocessor.models import ToolStatus
from ai_material_preprocessor.services.tool_versions import inspect_tool_versions


class FakeRunner:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return CommandResult(request.command, 0, self.stdout, "", 0.01)


def test_version_inspection_uses_package_metadata_for_python_api() -> None:
    result = inspect_tool_versions(
        {"markitdown": ToolStatus("markitdown", "Python API")},
        runner=FakeRunner(),
        package_lookup=lambda _: "0.1.6",
    )
    assert result["markitdown"].version == "0.1.6"
    assert result["markitdown"].detail == ""


def test_version_inspection_marks_outdated_external_tool() -> None:
    result = inspect_tool_versions(
        {"ffmpeg": ToolStatus("ffmpeg", "D:/tools/ffmpeg.exe")},
        runner=FakeRunner("ffmpeg version 4.4"),
    )
    assert result["ffmpeg"].version == "ffmpeg version 4.4"
    assert "版本异常" in result["ffmpeg"].detail


def test_missing_package_version_is_a_warning_not_a_missing_tool() -> None:
    def missing(_: str) -> str:
        raise PackageNotFoundError

    result = inspect_tool_versions(
        {"rapidocr": ToolStatus("rapidocr", "Python API")},
        runner=FakeRunner(),
        package_lookup=missing,
    )
    assert result["rapidocr"].available
    assert "版本检测失败" in result["rapidocr"].detail


def test_libreoffice_version_uses_console_sibling_when_available(tmp_path) -> None:
    executable = tmp_path / "program" / "soffice.exe"
    console = executable.with_suffix(".com")
    console.parent.mkdir(parents=True)
    executable.touch()
    console.touch()
    runner = FakeRunner("LibreOffice 26.2.5.2")

    result = inspect_tool_versions(
        {"libreoffice": ToolStatus("libreoffice", str(executable))},
        runner=runner,
    )

    assert runner.requests[0].executable == str(console)
    assert result["libreoffice"].version == "LibreOffice 26.2.5.2"
