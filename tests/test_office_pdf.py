from pathlib import Path

import pytest

from ai_material_preprocessor.converters import office_pdf
from ai_material_preprocessor.converters.common import ConversionError
from ai_material_preprocessor.converters.office_pdf import select_pdf_backend


@pytest.mark.parametrize(
    ("suffix", "word", "powerpoint", "libreoffice", "expected"),
    [
        (".docx", "winword.exe", None, "soffice.exe", "office-word"),
        (".pptx", None, "powerpnt.exe", "soffice.exe", "office-powerpoint"),
        (".docx", None, None, "soffice.exe", "libreoffice"),
    ],
)
def test_backend_selection_prefers_microsoft_office(
    suffix: str,
    word: str | None,
    powerpoint: str | None,
    libreoffice: str | None,
    expected: str,
) -> None:
    assert select_pdf_backend(Path(f"file{suffix}"), libreoffice, word, powerpoint) == expected


def test_backend_selection_rejects_unsupported_input() -> None:
    with pytest.raises(ConversionError):
        select_pdf_backend(Path("file.xlsx"), None, "winword.exe", "powerpnt.exe")


def test_pdf_is_written_directly_to_selected_output_directory(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "lesson.docx"
    source.write_bytes(b"docx")
    output_root = tmp_path / "chosen-folder"

    def fake_run(command: list[str]):
        output = Path(command[command.index("-OutputPath") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"pdf")

    monkeypatch.setattr(office_pdf, "run_command", fake_run)

    result = office_pdf.to_pdf(source, output_root, None, "winword.exe", None)

    assert result == output_root / "lesson.pdf"
    assert result.is_file()
    assert not (output_root / "PDF").exists()
