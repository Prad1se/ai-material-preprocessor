from __future__ import annotations

import shutil
import warnings
from collections.abc import Callable
from pathlib import Path

from ..errors import ErrorCode
from ..infrastructure.processes import CancellationToken
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
    cancellation: CancellationToken | None = None,
    tool_versions: dict[str, str] | None = None,
) -> Path:
    cli_output: Path | None = None

    def ensure_not_cancelled() -> None:
        if cancellation and cancellation.is_cancelled:
            raise ConversionError(
                "任务已取消，原文件没有改动。",
                code=ErrorCode.CANCELLED,
                retryable=True,
            )

    ensure_not_cancelled()
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
        ensure_not_cancelled()
        text = getattr(result, "text_content", None) or getattr(result, "markdown", None)
        if text is None:
            raise ConversionError("MarkItDown 未返回 Markdown 内容。")
        markdown = str(text)
    elif executable and executable != "Python API":
        output_root.mkdir(parents=True, exist_ok=True)
        cli_output = unique_path(output_root / f"{source.stem}.md")
        try:
            run_command(
                [executable, str(source), "-o", str(cli_output)],
                tool_name="MarkItDown",
                cancellation=cancellation,
            )
            ensure_not_cancelled()
            markdown = cli_output.read_text(encoding="utf-8")
        except Exception:
            if cli_output.exists():
                cli_output.unlink()
            raise
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
        try:
            ensure_not_cancelled()
            result = enhance_document(
                source=source,
                raw_markdown=markdown,
                output_dir=enhanced_dir,
                options=enhancement_options or EnhancementOptions(),
                ocr_engine=ocr_engine,
                tool_versions=tool_versions,
            )
            ensure_not_cancelled()
        except Exception:
            if cancellation and cancellation.is_cancelled and enhanced_dir.exists():
                shutil.rmtree(enhanced_dir, ignore_errors=True)
            raise
        finally:
            if cli_output and cli_output.exists():
                cli_output.unlink()
        if quality_callback is not None:
            quality_callback(result.quality)
        return result.content
    if cli_output is not None:
        return cli_output
    output = unique_path(output_root / f"{source.stem}.md")
    ensure_not_cancelled()
    output.write_text(markdown, encoding="utf-8")
    return output
