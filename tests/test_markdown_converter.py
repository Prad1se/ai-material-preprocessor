import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_material_preprocessor.converters import markdown as markdown_converter
from ai_material_preprocessor.converters.common import ConversionError
from ai_material_preprocessor.converters.markdown import to_markdown
from ai_material_preprocessor.errors import ErrorCode
from ai_material_preprocessor.infrastructure.processes import CancellationToken
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


def test_markdown_checks_cancellation_before_in_process_conversion(tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.write_bytes(b"fake-docx")
    token = CancellationToken()
    token.cancel()

    with pytest.raises(ConversionError) as raised:
        to_markdown(
            source,
            tmp_path / "output",
            converter=FakeMarkItDown(),
            cancellation=token,
        )

    assert raised.value.code is ErrorCode.CANCELLED
    assert not (tmp_path / "output").exists()


def test_markdown_cli_fallback_returns_exactly_one_raw_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.write_bytes(b"fake-docx")
    output_root = tmp_path / "output"
    monkeypatch.setitem(sys.modules, "markitdown", None)

    def fake_run(command: list[str], **_kwargs):
        output = Path(command[command.index("-o") + 1])
        output.write_text("# CLI result", encoding="utf-8")

    monkeypatch.setattr(markdown_converter, "run_command", fake_run)

    result = to_markdown(source, output_root, executable="markitdown.exe")

    assert result == output_root / "lesson.md"
    assert result.read_text(encoding="utf-8") == "# CLI result"
    assert list(output_root.glob("*.md")) == [result]
