from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .document_provenance import extract_provenance
from .files import safe_component
from .markdown_cleaning import clean_markdown, repair_image_paths
from .markdown_quality import check_quality, preserve_original_issues
from .markdown_splitting import estimate_tokens, split_markdown
from .markdown_types import MarkdownChunk, QualityIssue, QualityReport

__all__ = [
    "EnhancementOptions",
    "EnhancementResult",
    "MarkdownChunk",
    "QualityIssue",
    "QualityReport",
    "check_quality",
    "clean_markdown",
    "enhance_document",
    "estimate_tokens",
    "repair_image_paths",
    "split_markdown",
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
class EnhancementResult:
    raw: Path
    content: Path
    quality: QualityReport
    chunks: tuple[Path, ...]
    manifest: Path
    readme: Path


class OCREngine(Protocol):
    def extract(self, source: Path) -> list[tuple[str, str, float]]: ...


def _deduplicate_ocr_pages(
    extracted: list[tuple[str, str, float]],
) -> list[tuple[str, str, float]]:
    if len(extracted) < 3:
        return extracted

    def normalized(value: str) -> str:
        return re.sub(r"\d+", "<num>", re.sub(r"\s+", " ", value.strip()))

    page_lines = [
        {normalized(line) for line in text.splitlines() if line.strip()} for _, text, _ in extracted
    ]
    counts = Counter(line for lines in page_lines for line in lines)
    threshold = max(3, math.ceil(len(extracted) * 0.6))
    repeated = {line for line, count in counts.items() if count >= threshold}
    if not repeated:
        return extracted
    cleaned: list[tuple[str, str, float]] = []
    for label, text, confidence in extracted:
        content = "\n".join(
            line for line in text.splitlines() if normalized(line) not in repeated
        ).strip()
        if content:
            cleaned.append((label, content, confidence))
    return cleaned


def enhance_document(
    *,
    source: Path,
    raw_markdown: str,
    output_dir: Path,
    options: EnhancementOptions,
    ocr_engine: OCREngine | None = None,
    tool_versions: dict[str, str] | None = None,
) -> EnhancementResult:
    output_dir.mkdir(parents=True, exist_ok=False)
    raw_path = output_dir / "raw.md"
    raw_path.write_text(raw_markdown, encoding="utf-8")
    cleaned = clean_markdown(raw_markdown, source_suffix=source.suffix)
    cleaned = repair_image_paths(cleaned, source_dir=source.parent, output_dir=output_dir)
    ocr_pages: list[tuple[str, str, float]] = []
    if options.ocr_enabled:
        if ocr_engine is None:
            from .ocr import RapidOCREngine

            ocr_engine = RapidOCREngine()
        ocr_pages = _deduplicate_ocr_pages(ocr_engine.extract(source))
        if ocr_pages:
            sections = ["## OCR 补充文本"]
            for label, text, confidence in ocr_pages:
                sections.extend(
                    ["", f"### {label}（平均置信度 {confidence:.1%}）", "", text.strip()]
                )
            cleaned = cleaned.rstrip() + "\n\n" + "\n".join(sections) + "\n"
    content_path = output_dir / "content.md"
    content_path.write_text(cleaned, encoding="utf-8")
    report = check_quality(
        cleaned,
        base_dir=output_dir,
        max_tokens=options.max_tokens,
        source_suffix=source.suffix,
    )
    original_report = check_quality(
        raw_markdown,
        base_dir=source.parent,
        max_tokens=options.max_tokens,
        source_suffix=source.suffix,
    )
    report = preserve_original_issues(report, original_report, codes={"heading_jump"})

    chunk_paths: list[Path] = []
    chunks: tuple[MarkdownChunk, ...] = ()
    if options.split_enabled:
        candidates = split_markdown(
            cleaned,
            target_tokens=options.target_tokens,
            max_tokens=options.max_tokens,
            source_suffix=source.suffix,
        )
        if len(candidates) > 1:
            chunks = candidates
            chunk_dir = output_dir / "chunks"
            chunk_dir.mkdir()
            for chunk in chunks:
                name = f"{chunk.index:03d}-{safe_component(chunk.title, f'chunk-{chunk.index}')}.md"
                path = chunk_dir / name
                path.write_text(chunk.content, encoding="utf-8")
                chunk_paths.append(path)
    readme = output_dir / "README.md"
    readme.write_text(
        "# AI 资料包\n\n"
        f"来源：`{source.name}`\n\n"
        "## 从这里开始\n\n"
        + ("- 优先按顺序读取 `chunks/` 中的分段。\n" if chunk_paths else "- 读取 `content.md`。\n")
        + "- `raw.md` 是未经清洗的 MarkItDown 原始结果，可用于核对。\n"
        "- `manifest.json` 提供机器可读的文件清单与长度信息。\n",
        encoding="utf-8",
    )
    source_hash = hashlib.sha256()
    source_digest: str | None = None
    if source.is_file():
        with source.open("rb") as source_file:
            for block in iter(lambda: source_file.read(1024 * 1024), b""):
                source_hash.update(block)
        source_digest = source_hash.hexdigest()
    provenance = extract_provenance(cleaned, source_suffix=source.suffix)
    assets_dir = output_dir / "assets"
    assets = (
        sorted(
            path.relative_to(output_dir).as_posix()
            for path in assets_dir.rglob("*")
            if path.is_file()
        )
        if assets_dir.is_dir()
        else []
    )
    manifest = {
        "package_type": "ai_document_package",
        "format_version": 2,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "enhanced",
        "source": {
            "name": source.name,
            "sha256": source_digest,
            "format": source.suffix.lower(),
        },
        "tools": dict(sorted((tool_versions or {}).items())),
        "main_markdown": "content.md",
        "chunks": [
            {
                "index": chunk.index,
                "title": chunk.title,
                "estimated_tokens": chunk.estimated_tokens,
                "file": f"chunks/{path.name}",
                "sources": list(chunk.source_labels),
            }
            for chunk, path in zip(chunks, chunk_paths, strict=True)
        ],
        "assets": assets,
        "provenance": [span.to_dict() for span in provenance],
        "ocr": {
            "enabled": options.ocr_enabled,
            "pages": [
                {
                    "label": label,
                    "confidence": confidence,
                    "low_confidence": confidence < 0.7,
                }
                for label, _text, confidence in ocr_pages
            ],
        },
        "warnings": [
            {
                "code": issue.code,
                "severity": issue.severity,
                "message": issue.message,
                "line": issue.line,
                "source_label": issue.source_label,
            }
            for issue in report.issues
            if issue.severity in {"warning", "error"}
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return EnhancementResult(
        raw=raw_path,
        content=content_path,
        quality=report,
        chunks=tuple(chunk_paths),
        manifest=manifest_path,
        readme=readme,
    )
