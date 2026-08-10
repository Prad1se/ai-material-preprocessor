from __future__ import annotations

import warnings
from collections.abc import Callable
from pathlib import Path

from ..services.document_enhancement import (
    EnhancementOptions,
    QualityReport,
    enhance_document,
)
from ..services.files import unique_path
from .common import ConversionError, run_command

SUPPORTED_EXTENSIONS = {
    ".docx",
    ".pptx",
    ".xlsx",
    ".pdf",
    ".html",
    ".htm",
    ".csv",
    ".json",
    ".xml",
    ".epub",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


def to_markdown(
    source: Path,
    output_root: Path,
    executable: str | None = None,
    *,
    converter=None,
    enhance: bool = False,
    enhancement_options: EnhancementOptions | None = None,
    ocr_engine=None,
    quality_callback: Callable[[QualityReport], None] | None = None,
) -> Path:
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ConversionError(f"当前原型未开放 {source.suffix} → Markdown。")
    if converter is None:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Couldn't find ffmpeg or avconv.*")
                from markitdown import MarkItDown

            converter = MarkItDown(enable_plugins=False)
        except ImportError:
            converter = None

    if converter is not None:
        result = converter.convert_local(source)
        text = getattr(result, "text_content", None) or getattr(result, "markdown", None)
        if text is None:
            raise ConversionError("MarkItDown 未返回 Markdown 内容。")
        markdown = str(text)
    elif executable and executable != "Python API":
        output_root.mkdir(parents=True, exist_ok=True)
        output = unique_path(output_root / f"{source.stem}.md")
        run_command([executable, str(source), "-o", str(output)])
        markdown = output.read_text(encoding="utf-8")
    else:
        raise ConversionError("未检测到 MarkItDown。")
    output_root.mkdir(parents=True, exist_ok=True)
    if enhance:
        base = output_root / f"{source.stem}_AI资料包"
        enhanced_dir = base
        counter = 2
        while enhanced_dir.exists():
            enhanced_dir = output_root / f"{base.name}_{counter}"
            counter += 1
        result = enhance_document(
            source=source,
            raw_markdown=markdown,
            output_dir=enhanced_dir,
            options=enhancement_options or EnhancementOptions(),
            ocr_engine=ocr_engine,
        )
        if quality_callback is not None:
            quality_callback(result.quality)
        return result.content
    output = unique_path(output_root / f"{source.stem}.md")
    output.write_text(markdown, encoding="utf-8")
    return output
