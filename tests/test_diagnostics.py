import json
from pathlib import Path
from types import SimpleNamespace

from ai_material_preprocessor.diagnostics import run_self_test
from ai_material_preprocessor.models import ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG


class FakeMarkItDown:
    def convert_local(self, source: Path):
        return SimpleNamespace(text_content="# 自检成功")


def test_self_test_writes_machine_readable_report(tmp_path: Path) -> None:
    tools = {
        name: ToolStatus(name, None)
        for name in (
            "markitdown",
            "ffmpeg",
            "ffprobe",
            "exiftool",
            "libreoffice",
            "winword",
            "powerpoint",
        )
    }
    tools["markitdown"] = ToolStatus("markitdown", "Python API", "内置")

    report_path = run_self_test(
        tmp_path,
        config=DEFAULT_CONFIG,
        tools=tools,
        markdown_converter=FakeMarkItDown(),
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["application_version"] == "2.0.0rc1"
    assert report["overall"] == "passed"
    assert report["checks"]["markitdown"]["passed"] is True
    assert Path(report["checks"]["markitdown"]["output"]).is_file()
    assert report["tools"]["ffmpeg"]["available"] is False
