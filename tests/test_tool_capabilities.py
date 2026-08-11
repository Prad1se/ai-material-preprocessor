from ai_material_preprocessor.models import ToolStatus
from ai_material_preprocessor.services.tool_capabilities import (
    CapabilityState,
    build_tool_capabilities,
)


def test_capabilities_distinguish_available_missing_warning_and_optional() -> None:
    tools = {
        "markitdown": ToolStatus("markitdown", "Python API", version="0.1.6"),
        "ffmpeg": ToolStatus("ffmpeg", "D:/tools/ffmpeg.exe", detail="版本检测失败"),
        "ffprobe": ToolStatus("ffprobe", None),
        "exiftool": ToolStatus("exiftool", None),
        "libreoffice": ToolStatus("libreoffice", None),
        "winword": ToolStatus("winword", "C:/Office/WINWORD.EXE"),
        "powerpoint": ToolStatus("powerpoint", "C:/Office/POWERPNT.EXE"),
        "rapidocr": ToolStatus("rapidocr", None),
    }

    result = {item.key: item for item in build_tool_capabilities(tools)}

    assert result["markitdown"].state is CapabilityState.AVAILABLE
    assert result["ffmpeg"].state is CapabilityState.VERSION_WARNING
    assert result["ffprobe"].state is CapabilityState.MISSING
    assert result["rapidocr"].optional is True
    assert "可选" in result["rapidocr"].status_text
    assert result["ffprobe"].installation_hint


def test_capability_path_is_never_required_for_python_api_tools() -> None:
    tools = {
        "markitdown": ToolStatus("markitdown", "Python API", version="0.1.6"),
        "rapidocr": ToolStatus("rapidocr", "Python API", version="3.9.0"),
    }

    result = {item.key: item for item in build_tool_capabilities(tools)}

    assert result["markitdown"].custom_path_supported is True
    assert result["rapidocr"].custom_path_supported is False
