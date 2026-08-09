from pathlib import Path

from ai_material_preprocessor.services.environment import (
    candidate_paths,
    resolve_ffmpeg,
    resolve_tool,
)


def test_explicit_override_has_precedence(tmp_path: Path) -> None:
    configured = tmp_path / "custom" / "ffmpeg.exe"
    configured.parent.mkdir()
    configured.touch()
    bundled = tmp_path / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    bundled.parent.mkdir(parents=True)
    bundled.touch()

    result = resolve_tool("ffmpeg", str(configured), [bundled], path_lookup=lambda _: None)

    assert result.path == str(configured)
    assert result.source == "配置"


def test_bundled_binary_precedes_path(tmp_path: Path) -> None:
    bundled = tmp_path / "ffmpeg.exe"
    bundled.touch()

    result = resolve_tool("ffmpeg", "", [bundled], path_lookup=lambda _: "C:/Windows/ffmpeg.exe")

    assert result.path == str(bundled)
    assert result.source == "随程序提供"


def test_path_is_used_as_last_fallback() -> None:
    result = resolve_tool(
        "ffmpeg", "", [Path("C:/missing/ffmpeg.exe")], path_lookup=lambda _: "D:/bin/ffmpeg.exe"
    )
    assert result.path == "D:/bin/ffmpeg.exe"
    assert result.source == "系统 PATH"


def test_candidate_paths_include_project_tools(tmp_path: Path) -> None:
    paths = candidate_paths("ffprobe", tmp_path, None)
    assert tmp_path / "tools" / "ffmpeg" / "bin" / "ffprobe.exe" in paths


def test_ffmpeg_uses_imageio_bundled_binary_as_final_fallback(tmp_path: Path) -> None:
    bundled = tmp_path / "ffmpeg.exe"
    bundled.touch()
    result = resolve_ffmpeg(
        "",
        [],
        path_lookup=lambda _: None,
        imageio_getter=lambda: str(bundled),
    )
    assert result.path == str(bundled)
    assert result.source == "imageio-ffmpeg"
