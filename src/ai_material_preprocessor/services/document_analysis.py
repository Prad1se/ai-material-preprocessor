from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .markdown_cleaning import clean_markdown
from .markdown_quality import check_quality, preserve_original_issues
from .markdown_splitting import split_markdown
from .markdown_types import MarkdownChunk, QualityReport

OCRPage = tuple[str, str, float]

__all__ = [
    "DocumentAnalysis",
    "EnhancementOptions",
    "OCRPage",
    "analyze_document",
    "deduplicate_ocr_pages",
    "prepare_document_markdown",
]


@dataclass(frozen=True)
class EnhancementOptions:
    split_enabled: bool = True
    target_tokens: int = 4000
    max_tokens: int = 6000
    ocr_enabled: bool = False

    def __post_init__(self) -> None:
        if self.target_tokens < 20:
            raise ValueError("目标长度不能小于 20 个估算 token。")
        if self.max_tokens < self.target_tokens:
            raise ValueError("长度上限不能小于目标长度。")


@dataclass(frozen=True)
class DocumentAnalysis:
    cleaned_markdown: str
    quality: QualityReport
    chunks: tuple[MarkdownChunk, ...]
    ocr_pages: tuple[OCRPage, ...]


def prepare_document_markdown(raw_markdown: str, *, source_suffix: str) -> str:
    """Run the deterministic Markdown cleanup shared by output and preview flows."""
    return clean_markdown(raw_markdown, source_suffix=source_suffix)


def deduplicate_ocr_pages(extracted: tuple[OCRPage, ...]) -> tuple[OCRPage, ...]:
    """Remove repeated OCR headers and footers without discarding page-specific text."""
    if len(extracted) < 3:
        return extracted

    def normalized(value: str) -> str:
        return re.sub(r"\d+", "<num>", re.sub(r"\s+", " ", value.strip()))

    page_lines = [
        {normalized(line) for line in text.splitlines() if line.strip()}
        for _label, text, _ in extracted
    ]
    counts = Counter(line for lines in page_lines for line in lines)
    threshold = max(3, math.ceil(len(extracted) * 0.6))
    repeated = {line for line, count in counts.items() if count >= threshold}
    if not repeated:
        return extracted
    cleaned: list[OCRPage] = []
    for label, text, confidence in extracted:
        content = "\n".join(
            line for line in text.splitlines() if normalized(line) not in repeated
        ).strip()
        if content:
            cleaned.append((label, content, confidence))
    return tuple(cleaned)


def _append_ocr_pages(markdown: str, pages: tuple[OCRPage, ...]) -> str:
    if not pages:
        return markdown
    sections = ["## OCR 补充文本"]
    for label, text, confidence in pages:
        sections.extend(["", f"### {label}（平均置信度 {confidence:.1%}）", "", text.strip()])
    return markdown.rstrip() + "\n\n" + "\n".join(sections) + "\n"


def analyze_document(
    *,
    raw_markdown: str,
    source_suffix: str,
    base_dir: Path,
    options: EnhancementOptions,
    ocr_pages: tuple[OCRPage, ...] = (),
    append_ocr_pages: bool = False,
    cleaned_markdown: str | None = None,
    original_base_dir: Path | None = None,
) -> DocumentAnalysis:
    """Analyze converted Markdown without writing files or invoking external tools."""
    cleaned = (
        prepare_document_markdown(raw_markdown, source_suffix=source_suffix)
        if cleaned_markdown is None
        else cleaned_markdown
    )
    normalized_ocr = deduplicate_ocr_pages(ocr_pages)
    if append_ocr_pages:
        cleaned = _append_ocr_pages(cleaned, normalized_ocr)
    quality = check_quality(
        cleaned,
        base_dir=base_dir,
        max_tokens=options.max_tokens,
        source_suffix=source_suffix,
    )
    original_quality = check_quality(
        raw_markdown,
        base_dir=original_base_dir or base_dir,
        max_tokens=options.max_tokens,
        source_suffix=source_suffix,
    )
    quality = preserve_original_issues(quality, original_quality, codes={"heading_jump"})
    chunks = (
        split_markdown(
            cleaned,
            target_tokens=options.target_tokens,
            max_tokens=options.max_tokens,
            source_suffix=source_suffix,
        )
        if options.split_enabled
        else ()
    )
    return DocumentAnalysis(cleaned, quality, chunks, normalized_ocr)
