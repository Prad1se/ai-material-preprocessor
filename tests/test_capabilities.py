from ai_material_preprocessor.apps.documents.policy import (
    DOCUMENT_OPERATIONS,
    DOCUMENT_TOOL_NAMES,
)
from ai_material_preprocessor.apps.video.policy import VIDEO_OPERATIONS, VIDEO_TOOL_NAMES
from ai_material_preprocessor.capabilities import available_operations
from ai_material_preprocessor.models import Operation, ToolStatus
from ai_material_preprocessor.services.environment import select_tools


def tools(**available: bool) -> dict[str, ToolStatus]:
    names = (
        "markitdown",
        "ffmpeg",
        "ffprobe",
        "exiftool",
        "libreoffice",
        "winword",
        "powerpoint",
        "rapidocr",
    )
    return {
        name: ToolStatus(name, f"C:/tools/{name}.exe" if available.get(name, False) else None)
        for name in names
    }


def test_docx_exposes_ai_and_pdf_when_engines_exist() -> None:
    result = available_operations("lesson.docx", tools(markitdown=True, winword=True))
    assert result == [
        Operation.TO_MARKDOWN,
        Operation.TO_PDF,
        Operation.DOCUMENT_CONTEXT_PACK,
    ]


def test_pdf_only_exposes_markdown() -> None:
    result = available_operations("paper.pdf", tools(markitdown=True))
    assert result == [Operation.TO_MARKDOWN, Operation.DOCUMENT_CONTEXT_PACK]


def test_context_pack_requires_markitdown() -> None:
    assert available_operations("paper.pdf", tools()) == []


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


def test_available_operations_can_be_filtered_by_workspace_policy() -> None:
    detected = tools(markitdown=True, winword=True, ffmpeg=True)

    assert available_operations(
        "lesson.docx",
        detected,
        allowed_operations=DOCUMENT_OPERATIONS,
    ) == [
        Operation.TO_MARKDOWN,
        Operation.TO_PDF,
        Operation.DOCUMENT_CONTEXT_PACK,
    ]
    assert available_operations(
        "clip.mp4",
        detected,
        allowed_operations=VIDEO_OPERATIONS,
    ) == [
        Operation.COMPRESS_VIDEO,
        Operation.EXTRACT_AUDIO,
        Operation.STANDARDIZE_MP4,
        Operation.KEYFRAMES_CONTACT_SHEET,
        Operation.RENAME_VIDEO,
        Operation.ORGANIZE_VIDEO,
    ]


def test_detected_tools_can_be_projected_to_workspace_specific_views() -> None:
    detected = tools(markitdown=True, rapidocr=True, ffmpeg=True, ffprobe=True, exiftool=True)

    assert set(select_tools(detected, DOCUMENT_TOOL_NAMES)) == DOCUMENT_TOOL_NAMES
    assert set(select_tools(detected, VIDEO_TOOL_NAMES)) == VIDEO_TOOL_NAMES
