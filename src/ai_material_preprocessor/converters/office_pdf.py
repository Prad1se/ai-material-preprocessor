from __future__ import annotations

import tempfile
from pathlib import Path

from ..services.config import resource_path
from ..services.files import unique_path
from .common import ConversionError, run_command


WORD_EXTENSIONS = {".doc", ".docx"}
POWERPOINT_EXTENSIONS = {".ppt", ".pptx"}


def select_pdf_backend(
    source: Path,
    libreoffice: str | None,
    winword: str | None,
    powerpoint: str | None,
) -> str:
    suffix = source.suffix.lower()
    if suffix in WORD_EXTENSIONS:
        if winword:
            return "office-word"
        if libreoffice:
            return "libreoffice"
    elif suffix in POWERPOINT_EXTENSIONS:
        if powerpoint:
            return "office-powerpoint"
        if libreoffice:
            return "libreoffice"
    else:
        raise ConversionError("PDF 转换目前只支持 Word 和 PowerPoint。")
    raise ConversionError("未检测到可处理该文件的 Microsoft Office 或 LibreOffice。")


def to_pdf(
    source: Path,
    output_root: Path,
    libreoffice: str | None,
    winword: str | None,
    powerpoint: str | None,
) -> Path:
    backend = select_pdf_backend(source, libreoffice, winword, powerpoint)

    output_root.mkdir(parents=True, exist_ok=True)
    output = unique_path(output_root / f"{source.stem}.pdf")

    if backend == "libreoffice":
        # LibreOffice always chooses the source stem. Convert in a temporary
        # folder first so an existing result can never be overwritten.
        with tempfile.TemporaryDirectory(prefix="office-pdf-", dir=output_root) as temporary:
            temporary_path = Path(temporary)
            run_command([
                libreoffice, "--headless", "--convert-to", "pdf",
                "--outdir", str(temporary_path), str(source),
            ])
            generated = temporary_path / f"{source.stem}.pdf"
            if not generated.exists():
                raise ConversionError("LibreOffice 未生成预期的 PDF。")
            generated.replace(output)
        return output

    office_kind = "word" if backend == "office-word" else "powerpoint"

    script = resource_path("scripts", "office_to_pdf.ps1")
    run_command([
        "powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
        "-File", str(script), "-InputPath", str(source),
        "-OutputPath", str(output), "-Kind", office_kind,
    ])
    if not output.exists():
        raise ConversionError("Microsoft Office 未生成预期的 PDF。")
    return output
