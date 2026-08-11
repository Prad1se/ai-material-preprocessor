from ai_material_preprocessor.capabilities import available_operations
from ai_material_preprocessor.models import Operation, ToolStatus


def tools(**available: bool) -> dict[str, ToolStatus]:
    names = (
        "markitdown",
        "ffmpeg",
        "ffprobe",
        "exiftool",
        "libreoffice",
        "winword",
        "powerpoint",
    )
    return {
        name: ToolStatus(name, f"C:/tools/{name}.exe" if available.get(name, False) else None)
        for name in names
    }


def test_docx_exposes_ai_and_pdf_when_engines_exist() -> None:
    result = available_operations("lesson.docx", tools(markitdown=True, winword=True))
    assert result == [Operation.TO_MARKDOWN, Operation.TO_PDF]


def test_pdf_only_exposes_markdown() -> None:
    result = available_operations("paper.pdf", tools(markitdown=True))
    assert result == [Operation.TO_MARKDOWN]


def test_video_conversion_requires_ffmpeg_but_rename_remains_available() -> None:
    result = available_operations("clip.mp4", tools())
    assert result == [Operation.RENAME_VIDEO, Operation.ORGANIZE_VIDEO]


def test_video_with_ffmpeg_exposes_all_creation_operations() -> None:
    result = available_operations("clip.mov", tools(ffmpeg=True, ffprobe=True))
    assert result == [
        Operation.COMPRESS_VIDEO,
        Operation.EXTRACT_AUDIO,
        Operation.STANDARDIZE_MP4,
        Operation.KEYFRAMES_CONTACT_SHEET,
        Operation.RENAME_VIDEO,
        Operation.ORGANIZE_VIDEO,
    ]


def test_unknown_extension_has_no_operations() -> None:
    assert available_operations("archive.unknown", tools(markitdown=True, ffmpeg=True)) == []
