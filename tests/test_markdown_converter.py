from pathlib import Path
from types import SimpleNamespace

from ai_material_preprocessor.converters.markdown import to_markdown
from ai_material_preprocessor.services.document_enhancement import EnhancementOptions


class FakeMarkItDown:
    def convert_local(self, source: Path):
        return SimpleNamespace(text_content="# 标题\n\n内容")


def test_markdown_uses_python_api_and_never_overwrites(tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.write_bytes(b"fake-docx")
    output_root = tmp_path / "output"
    existing = output_root / "lesson.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("old", encoding="utf-8")

    result = to_markdown(source, output_root, converter=FakeMarkItDown())

    assert result.name == "lesson_2.md"
    assert result.read_text(encoding="utf-8") == "# 标题\n\n内容"
    assert existing.read_text(encoding="utf-8") == "old"


def test_markdown_enhanced_mode_preserves_raw_result(tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.write_bytes(b"fake-docx")
    result = to_markdown(
        source,
        tmp_path / "output",
        converter=FakeMarkItDown(),
        enhance=True,
        enhancement_options=EnhancementOptions(split_enabled=False),
    )
    assert result.name == "content.md"
    assert result.parent.name == "lesson_AI资料包"
    assert (result.parent / "raw.md").read_text(encoding="utf-8") == "# 标题\n\n内容"
