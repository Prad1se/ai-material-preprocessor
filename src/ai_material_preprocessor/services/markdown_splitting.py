from __future__ import annotations

import math
import re

from .markdown_cleaning import HEADING_PATTERN
from .markdown_types import MarkdownChunk


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
    root_heading = next((block for block in blocks if re.match(r"^#\s+", block)), "")
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
        title_match = next(
            (HEADING_PATTERN.match(part) for part in group if HEADING_PATTERN.match(part)),
            None,
        )
        title = title_match.group(2) if title_match else f"分段 {index}"
        chunks.append(MarkdownChunk(index, title, content, estimate_tokens(content)))
    return tuple(chunks)
