from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .document_provenance import extract_provenance, source_label_for_line
from .markdown_cleaning import HEADING_PATTERN
from .markdown_types import MarkdownChunk


@dataclass(frozen=True)
class StructuredMarkdownBlock:
    content: str
    start_line: int
    end_line: int
    heading_context: tuple[str, ...]
    atomic: bool


def estimate_tokens(text: str) -> int:
    """Deterministic multilingual estimate; it is deliberately not model-specific."""
    cjk = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
    remainder = re.sub(r"[\u3400-\u9fff\uf900-\ufaff]", "", text)
    words = len(re.findall(r"\b[\w'-]+\b", remainder, flags=re.UNICODE))
    punctuation = len(re.findall(r"[^\w\s]", remainder, flags=re.UNICODE))
    return max(1, cjk + words + math.ceil(punctuation / 4))


def _sentence_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    in_math = False
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
        if line.strip() == "$$":
            if not in_math and current:
                blocks.append("\n".join(current).strip())
                current = []
            current.append(line)
            in_math = not in_math
            if not in_math:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        if in_math:
            current.append(line)
            continue
        if line.strip().startswith("$$") and line.strip().endswith("$$"):
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            blocks.append(line.strip())
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
    if estimate_tokens(text) <= limit or text.startswith(("```", "~~~", "|", "$$")):
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


def split_oversized_markdown_block(text: str, limit: int) -> tuple[str, ...]:
    """Reuse the document splitter's safe text fallback for a single block."""
    if limit < 1:
        raise ValueError("The block token limit must be positive.")
    return tuple(_split_oversized_text(text, limit))


def structured_markdown_blocks(text: str) -> tuple[StructuredMarkdownBlock, ...]:
    """Expose the existing structural parser without applying a job-specific budget."""
    lines = text.splitlines()
    headings: list[str] = []
    result: list[StructuredMarkdownBlock] = []

    def append(content: str, start_line: int, *, atomic: bool) -> None:
        nonlocal headings
        heading = HEADING_PATTERN.match(content)
        if heading:
            level = len(heading.group(1))
            headings = headings[: level - 1]
            headings.append(heading.group(2).strip())
        result.append(
            StructuredMarkdownBlock(
                content=content,
                start_line=start_line,
                end_line=start_line + content.count("\n"),
                heading_context=tuple(headings),
                atomic=atomic,
            )
        )

    normal: list[str] = []
    normal_start = 1

    def flush_normal() -> None:
        nonlocal normal
        if not normal:
            return
        segment = "\n".join(normal)
        cursor = 0
        for block in _sentence_blocks(segment):
            position = segment.find(block, cursor)
            if position < 0:
                position = cursor
            append(block, normal_start + segment.count("\n", 0, position), atomic=False)
            cursor = position + len(block)
        normal = []

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()
        fence = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence:
            flush_normal()
            opening = fence.group(1)
            marker = opening[0]
            minimum_length = len(opening)
            start = index
            fenced = [line]
            index += 1
            while index < len(lines):
                fenced.append(lines[index])
                if re.match(
                    rf"^\s*{re.escape(marker)}{{{minimum_length},}}\s*$",
                    lines[index],
                ):
                    index += 1
                    break
                index += 1
            append("\n".join(fenced), start + 1, atomic=True)
            continue
        if stripped.startswith("|"):
            flush_normal()
            start = index
            table: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                table.append(lines[index])
                index += 1
            append("\n".join(table), start + 1, atomic=True)
            continue
        if re.search(r"\]\((?:\./)?assets/[^)]+\)", line, flags=re.IGNORECASE):
            flush_normal()
            append(line.strip(), index + 1, atomic=True)
            index += 1
            continue
        if stripped == "$$" or (stripped.startswith("$$") and stripped.endswith("$$")):
            flush_normal()
            start = index
            math = [line]
            index += 1
            if stripped == "$$":
                while index < len(lines):
                    math.append(lines[index])
                    index += 1
                    if lines[index - 1].strip() == "$$":
                        break
            append("\n".join(math), start + 1, atomic=True)
            continue
        if not line.strip() or HEADING_PATTERN.match(line):
            flush_normal()
            if HEADING_PATTERN.match(line):
                append(line.strip(), index + 1, atomic=False)
            index += 1
            continue
        if not normal:
            normal_start = index + 1
        normal.append(line)
        index += 1
    flush_normal()
    return tuple(result)


def split_markdown(
    text: str,
    *,
    target_tokens: int = 4000,
    max_tokens: int = 6000,
    source_suffix: str = "",
) -> tuple[MarkdownChunk, ...]:
    if max_tokens < target_tokens:
        raise ValueError("长度上限不能小于目标长度。")
    blocks = _sentence_blocks(text)
    root_heading = next((block for block in blocks if re.match(r"^#\s+", block)), "")
    if root_heading:
        blocks.remove(root_heading)
    prefix_tokens = estimate_tokens(root_heading) if root_heading else 0
    usable_limit = max(1, max_tokens - prefix_tokens)
    expanded: list[str] = []
    for block in blocks:
        expanded.extend(_split_oversized_text(block, usable_limit))
    spans = extract_provenance(text, source_suffix=source_suffix)
    cursor = 0
    expanded_with_sources: list[tuple[str, str]] = []
    for block in expanded:
        position = text.find(block, cursor)
        if position < 0:
            position = text.find(block)
        if position >= 0:
            cursor = position + len(block)
            line_number = text.count("\n", 0, position) + 1
            label = source_label_for_line(spans, line_number)
        else:
            label = ""
        expanded_with_sources.append((block, label))
    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_tokens = prefix_tokens
    for block, label in expanded_with_sources:
        block_tokens = estimate_tokens(block)
        is_heading = HEADING_PATTERN.match(block) is not None
        current_ends_with_heading = bool(current and HEADING_PATTERN.match(current[-1][0]))
        should_flush = bool(
            current
            and (
                is_heading
                or current_tokens + block_tokens > max_tokens
                or (current_tokens + block_tokens > target_tokens and not current_ends_with_heading)
            )
        )
        if should_flush:
            groups.append(current)
            current = []
            current_tokens = prefix_tokens
        current.append((block, label))
        current_tokens += block_tokens
    if current or not groups:
        groups.append(current)

    chunks: list[MarkdownChunk] = []
    for index, group in enumerate(groups, start=1):
        group_blocks = [block for block, _label in group]
        parts = ([root_heading] if root_heading else []) + group_blocks
        content = "\n\n".join(parts).strip() + "\n"
        title_match = next(
            (HEADING_PATTERN.match(part) for part in group_blocks if HEADING_PATTERN.match(part)),
            None,
        )
        title = title_match.group(2) if title_match else f"分段 {index}"
        source_labels = tuple(dict.fromkeys(label for _block, label in group if label))
        chunks.append(MarkdownChunk(index, title, content, estimate_tokens(content), source_labels))
    return tuple(chunks)
