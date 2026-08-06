from __future__ import annotations

import json
import math
import re
import shutil
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse

from .files import safe_component, unique_path


IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PAGE_MARKER_PATTERN = re.compile(
    r"^<!--\s*(?:Slide number|Page)\s*:\s*\d+\s*-->$", re.IGNORECASE
)
SLIDE_MARKER_PATTERN = re.compile(
    r"^<!--\s*Slide number\s*:\s*\d+\s*-->$", re.IGNORECASE
)


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
class QualityIssue:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class QualityReport:
    score: int
    estimated_tokens: int
    heading_count: int
    image_count: int
    issues: tuple[QualityIssue, ...]

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "estimated_tokens": self.estimated_tokens,
            "heading_count": self.heading_count,
            "image_count": self.image_count,
            "issues": [asdict(issue) for issue in self.issues],
        }


@dataclass(frozen=True)
class MarkdownChunk:
    index: int
    title: str
    content: str
    estimated_tokens: int


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


def estimate_tokens(text: str) -> int:
    """Deterministic multilingual estimate; it is deliberately not model-specific."""
    cjk = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
    remainder = re.sub(r"[\u3400-\u9fff\uf900-\ufaff]", "", text)
    words = len(re.findall(r"\b[\w'-]+\b", remainder, flags=re.UNICODE))
    punctuation = len(re.findall(r"[^\w\s]", remainder, flags=re.UNICODE))
    return max(1, cjk + words + math.ceil(punctuation / 4))


def _page_sections(lines: list[str]) -> list[list[str]]:
    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if PAGE_MARKER_PATTERN.match(line.strip()) and current:
            sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)
    return sections


def _remove_repeated_page_text(lines: list[str]) -> list[str]:
    sections = _page_sections(lines)
    page_sections = [section for section in sections if any(
        PAGE_MARKER_PATTERN.match(line.strip()) for line in section
    )]
    if len(page_sections) < 3:
        return lines
    def normalized(value: str) -> str:
        return re.sub(r"\d+", "<num>", re.sub(r"\s+", " ", value.strip()))

    per_page = []
    for section in page_sections:
        candidates = {
            normalized(line)
            for line in section
            if line.strip()
            and not line.lstrip().startswith(("#", "<!--", "|", "```", "~~~"))
            and line.strip() != "---"
            and len(line.strip()) <= 160
        }
        per_page.append(candidates)
    counts = Counter(line for candidates in per_page for line in candidates)
    threshold = max(3, math.ceil(len(page_sections) * 0.6))
    repeated = {line for line, count in counts.items() if count >= threshold}
    if not repeated:
        return lines
    return [line for line in lines if normalized(line) not in repeated]


def _add_ppt_separators(lines: list[str]) -> list[str]:
    result: list[str] = []
    seen_slide = False
    for line in lines:
        if SLIDE_MARKER_PATTERN.match(line.strip()):
            if seen_slide:
                while result and not result[-1].strip():
                    result.pop()
                result.extend(["", "---", ""])
            seen_slide = True
        result.append(line)
    return result


def _label_excel_sheets(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            result.append(f"# 工作表：{match.group(1)}")
        else:
            result.append(line)
    return result


def clean_markdown(markdown: str, *, source_suffix: str = "") -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    suffix = source_suffix.lower()
    lines = _remove_repeated_page_text(lines)
    if suffix in {".ppt", ".pptx"}:
        lines = _add_ppt_separators(lines)
    elif suffix in {".xls", ".xlsx"}:
        lines = _label_excel_sheets(lines)

    result: list[str] = []
    in_fence = False
    fence_token = ""
    previous_heading = 0
    blank_count = 0
    for original in lines:
        line = original.rstrip()
        fence = re.match(r"^\s*(`{3,}|~{3,})([^`]*)$", line)
        if fence:
            token = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_token = token[0]
                language = re.sub(r"[^A-Za-z0-9_+.#-]", "", fence.group(2).strip())
                line = "```" + language
            elif token[0] == fence_token:
                in_fence = False
                fence_token = ""
                line = "```"
            result.append(line)
            blank_count = 0
            continue
        if in_fence:
            result.append(original.rstrip())
            continue
        if not line.strip():
            blank_count += 1
            if blank_count <= 1:
                result.append("")
            continue
        blank_count = 0
        heading = HEADING_PATTERN.match(line)
        if heading:
            level = len(heading.group(1))
            if previous_heading and level > previous_heading + 1:
                level = previous_heading + 1
            previous_heading = level
            line = f"{'#' * level} {heading.group(2).strip()}"
        line = re.sub(r"\\\((.+?)\\\)", r"$\1$", line)
        line = line.replace("\\[", "$$").replace("\\]", "$$")
        result.append(line)
    if in_fence:
        result.extend(["```"])
    while result and not result[-1].strip():
        result.pop()
    return "\n".join(result) + "\n"


def _local_image_path(raw: str, source_dir: Path) -> Path | None:
    value = raw.strip().strip("<>").split(maxsplit=1)[0]
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https", "data"}:
        return None
    if parsed.scheme == "file":
        value = unquote(parsed.path.lstrip("/"))
    value = value.replace("/", "\\") if "\\" in str(source_dir) else value.replace("\\", "/")
    candidate = Path(value)
    return candidate if candidate.is_absolute() else source_dir / candidate


def repair_image_paths(markdown: str, *, source_dir: Path, output_dir: Path) -> str:
    assets = output_dir / "assets"

    def replace(match: re.Match[str]) -> str:
        alt, raw = match.groups()
        source = _local_image_path(raw, source_dir)
        if source is None or not source.is_file():
            normalized = raw.replace("\\", "/")
            return f"![{alt}]({normalized})"
        assets.mkdir(parents=True, exist_ok=True)
        destination = unique_path(assets / safe_component(source.name, "image"))
        shutil.copy2(source, destination)
        return f"![{alt}](assets/{destination.name})"

    return IMAGE_PATTERN.sub(replace, markdown)


def check_quality(text: str, *, base_dir: Path, max_tokens: int) -> QualityReport:
    issues: list[QualityIssue] = []
    stripped = text.strip()
    estimated = estimate_tokens(text)
    if not stripped:
        issues.append(QualityIssue("empty_document", "error", "转换结果为空。"))
    elif estimated < 10:
        issues.append(QualityIssue("very_short", "warning", "内容很少，请核对转换是否完整。"))
    fences = sum(1 for line in text.splitlines() if re.match(r"^\s*(`{3,}|~{3,})", line))
    if fences % 2:
        issues.append(QualityIssue("unclosed_code_fence", "error", "存在未闭合的代码块。"))
    previous = 0
    for line in text.splitlines():
        heading = HEADING_PATTERN.match(line)
        if heading:
            level = len(heading.group(1))
            if previous and level > previous + 1:
                issues.append(QualityIssue("heading_jump", "warning", "仍存在跳级标题。"))
                break
            previous = level
    for match in IMAGE_PATTERN.finditer(text):
        raw = match.group(2).strip().strip("<>").split(maxsplit=1)[0]
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https", "data"}:
            candidate = Path(raw.replace("/", str(Path("/"))))
            if not candidate.is_absolute():
                candidate = base_dir / candidate
            if not candidate.is_file():
                issues.append(QualityIssue("missing_image", "warning", f"图片路径无效：{raw}"))
    if estimated > max_tokens:
        issues.append(QualityIssue(
            "oversized_document", "warning",
            f"全文约 {estimated} 个 token，超过配置上限 {max_tokens}；建议使用拆分结果。",
        ))
    deductions = {"error": 25, "warning": 10, "info": 2}
    score = max(0, 100 - sum(deductions.get(issue.severity, 5) for issue in issues))
    return QualityReport(
        score=score,
        estimated_tokens=estimated,
        heading_count=sum(1 for line in text.splitlines() if HEADING_PATTERN.match(line)),
        image_count=len(IMAGE_PATTERN.findall(text)),
        issues=tuple(issues),
    )


def _sentence_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if re.match(r"^\s*(`{3,}|~{3,})", line):
            in_fence = not in_fence
            current.append(line)
            if not in_fence:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        if in_fence:
            current.append(line)
            continue
        if HEADING_PATTERN.match(line):
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            blocks.append(line.strip())
            continue
        if not line.strip():
            if current:
                paragraph = "\n".join(current).strip()
                blocks.extend(part for part in re.split(r"(?<=[。！？.!?])\s*", paragraph) if part)
                current = []
            continue
        current.append(line)
    if current:
        paragraph = "\n".join(current).strip()
        blocks.extend(part for part in re.split(r"(?<=[。！？.!?])\s*", paragraph) if part)
    return [block for block in blocks if block]


def _split_oversized_text(text: str, limit: int) -> list[str]:
    if estimate_tokens(text) <= limit or text.startswith(("```", "|")):
        return [text]
    pieces: list[str] = []
    remaining = text
    while remaining:
        low, high = 1, len(remaining)
        best = 1
        while low <= high:
            middle = (low + high) // 2
            if estimate_tokens(remaining[:middle]) <= limit:
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        cut = best
        for separator in ("。", "！", "？", ".", ";", "，", ",", " "):
            candidate = remaining.rfind(separator, 0, best + 1)
            if candidate >= max(1, best // 2):
                cut = candidate + 1
                break
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return [piece for piece in pieces if piece]


def split_markdown(
    text: str, *, target_tokens: int = 4000, max_tokens: int = 6000
) -> tuple[MarkdownChunk, ...]:
    if max_tokens < target_tokens:
        raise ValueError("长度上限不能小于目标长度。")
    blocks = _sentence_blocks(text)
    root_heading = next(
        (block for block in blocks if re.match(r"^#\s+", block)), ""
    )
    if root_heading:
        blocks.remove(root_heading)
    prefix_tokens = estimate_tokens(root_heading) if root_heading else 0
    usable_limit = max(1, max_tokens - prefix_tokens)
    expanded: list[str] = []
    for block in blocks:
        expanded.extend(_split_oversized_text(block, usable_limit))
    groups: list[list[str]] = []
    current: list[str] = []
    current_tokens = prefix_tokens
    for block in expanded:
        block_tokens = estimate_tokens(block)
        if current and current_tokens + block_tokens > target_tokens:
            groups.append(current)
            current = []
            current_tokens = prefix_tokens
        if current and current_tokens + block_tokens > max_tokens:
            groups.append(current)
            current = []
            current_tokens = prefix_tokens
        current.append(block)
        current_tokens += block_tokens
    if current or not groups:
        groups.append(current)

    chunks: list[MarkdownChunk] = []
    for index, group in enumerate(groups, start=1):
        parts = ([root_heading] if root_heading else []) + group
        content = "\n\n".join(parts).strip() + "\n"
        title_match = next((HEADING_PATTERN.match(part) for part in group if HEADING_PATTERN.match(part)), None)
        title = title_match.group(2) if title_match else f"分段 {index}"
        chunks.append(MarkdownChunk(index, title, content, estimate_tokens(content)))
    return tuple(chunks)


def _deduplicate_ocr_pages(
    extracted: list[tuple[str, str, float]],
) -> list[tuple[str, str, float]]:
    if len(extracted) < 3:
        return extracted

    def normalized(value: str) -> str:
        return re.sub(r"\d+", "<num>", re.sub(r"\s+", " ", value.strip()))

    page_lines = [
        {normalized(line) for line in text.splitlines() if line.strip()}
        for _, text, _ in extracted
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
    *, source: Path, raw_markdown: str, output_dir: Path,
    options: EnhancementOptions, ocr_engine: OCREngine | None = None,
) -> EnhancementResult:
    output_dir.mkdir(parents=True, exist_ok=False)
    raw_path = output_dir / "raw.md"
    raw_path.write_text(raw_markdown, encoding="utf-8")
    cleaned = clean_markdown(raw_markdown, source_suffix=source.suffix)
    cleaned = repair_image_paths(cleaned, source_dir=source.parent, output_dir=output_dir)
    if options.ocr_enabled:
        if ocr_engine is None:
            from .ocr import RapidOCREngine
            ocr_engine = RapidOCREngine()
        extracted = _deduplicate_ocr_pages(ocr_engine.extract(source))
        if extracted:
            sections = ["## OCR 补充文本"]
            for label, text, confidence in extracted:
                sections.extend(["", f"### {label}（平均置信度 {confidence:.1%}）", "", text.strip()])
            cleaned = cleaned.rstrip() + "\n\n" + "\n".join(sections) + "\n"
    content_path = output_dir / "content.md"
    content_path.write_text(cleaned, encoding="utf-8")
    report = check_quality(cleaned, base_dir=output_dir, max_tokens=options.max_tokens)

    chunk_paths: list[Path] = []
    chunks: tuple[MarkdownChunk, ...] = ()
    if options.split_enabled:
        candidates = split_markdown(
            cleaned,
            target_tokens=options.target_tokens,
            max_tokens=options.max_tokens,
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
    manifest = {
        "package_type": "ai_document_package",
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": source.name,
        "source_path": str(source.resolve()),
        "source_size": source.stat().st_size if source.is_file() else None,
        "source_format": source.suffix.lower(),
        "ocr_enabled": options.ocr_enabled,
        "target_tokens": options.target_tokens,
        "max_tokens": options.max_tokens,
        "quality": report.to_dict(),
        "files": {
            "readme": "README.md",
            "raw": "raw.md",
            "content": "content.md",
            "assets": "assets" if (output_dir / "assets").is_dir() else None,
        },
        "chunk_count": len(chunks),
        "chunks": [
            {
                "index": chunk.index,
                "title": chunk.title,
                "estimated_tokens": chunk.estimated_tokens,
                "file": f"chunks/{path.name}",
            }
            for chunk, path in zip(chunks, chunk_paths, strict=True)
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return EnhancementResult(
        raw=raw_path, content=content_path, quality=report,
        chunks=tuple(chunk_paths), manifest=manifest_path,
        readme=readme,
    )
