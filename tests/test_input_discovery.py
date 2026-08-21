from pathlib import Path

from ai_material_preprocessor.services.input_discovery import discover_input_files


def test_discover_input_files_expands_folders_recursively_and_filters_supported_files(
    tmp_path: Path,
) -> None:
    document = tmp_path / "课程资料" / "第一章.docx"
    video = tmp_path / "视频" / "片段.mp4"
    ignored = tmp_path / "缓存.tmp"
    document.parent.mkdir()
    video.parent.mkdir()
    document.touch()
    video.touch()
    ignored.touch()

    result = discover_input_files([tmp_path])

    assert set(result) == {document.resolve(), video.resolve()}


def test_discover_input_files_deduplicates_explicit_and_folder_paths(tmp_path: Path) -> None:
    source = tmp_path / "资料.pdf"
    source.touch()

    result = discover_input_files([tmp_path, source])

    assert result == [source.resolve()]


def test_discover_input_files_accepts_app_specific_extension_policy(tmp_path: Path) -> None:
    document = tmp_path / "document.pdf"
    video = tmp_path / "video.mp4"
    document.touch()
    video.touch()

    assert discover_input_files([tmp_path], supported_extensions={".pdf"}) == [document.resolve()]
    assert discover_input_files([tmp_path], supported_extensions={".mp4"}) == [video.resolve()]
