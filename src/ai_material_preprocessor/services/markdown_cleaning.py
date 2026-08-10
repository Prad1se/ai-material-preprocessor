from __future__ import annotations

import math
import re
import shutil
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

from .files import safe_component, unique_path

IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PAGE_MARKER_PATTERN = re.compile(r"^<!--\s*(?:Slide number|Page)\s*:\s*\d+\s*-->$", re.IGNORECASE)
SLIDE_MARKER_PATTERN = re.compile(r"^<!--\s*Slide number\s*:\s*\d+\s*-->$", re.IGNORECASE)


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
    page_sections = [
        section
        for section in sections
        if any(PAGE_MARKER_PATTERN.match(line.strip()) for line in section)
    ]
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
        result.append(f"# 工作表：{match.group(1)}" if match else line)
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
        result.append("```")
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
