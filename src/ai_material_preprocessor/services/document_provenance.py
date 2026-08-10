from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import StrEnum


class ProvenanceKind(StrEnum):
    DOCUMENT = "document"
    PAGE = "page"
    SLIDE = "slide"
    WORKSHEET = "worksheet"
    OCR = "ocr"


@dataclass(frozen=True)
class SourceSpan:
    source_type: ProvenanceKind
    label: str
    ordinal: int | None
    start_line: int
    end_line: int
    confidence: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


SLIDE_MARKER = re.compile(r"^<!--\s*Slide number\s*:\s*(\d+)\s*-->$", re.IGNORECASE)
PAGE_MARKER = re.compile(r"^<!--\s*Page\s*:\s*(\d+)\s*-->$", re.IGNORECASE)
WORKSHEET_MARKER = re.compile(r"^#\s+工作表：(.+?)\s*$")
OCR_MARKER = re.compile(r"^###\s+(.+?)（平均置信度\s+([\d.]+)%）\s*$")


def _marker(line: str) -> tuple[ProvenanceKind, str, int | None, float | None] | None:
    stripped = line.strip()
    if match := SLIDE_MARKER.match(stripped):
        ordinal = int(match.group(1))
        return ProvenanceKind.SLIDE, f"幻灯片 {ordinal}", ordinal, None
    if match := PAGE_MARKER.match(stripped):
        ordinal = int(match.group(1))
        return ProvenanceKind.PAGE, f"第 {ordinal} 页", ordinal, None
    if match := WORKSHEET_MARKER.match(stripped):
        return ProvenanceKind.WORKSHEET, match.group(1).strip(), None, None
    if match := OCR_MARKER.match(stripped):
        return ProvenanceKind.OCR, match.group(1).strip(), None, float(match.group(2)) / 100
    return None


def extract_provenance(markdown: str, *, source_suffix: str = "") -> tuple[SourceSpan, ...]:
    lines = markdown.splitlines()
    markers: list[tuple[int, ProvenanceKind, str, int | None, float | None]] = []
    for line_number, line in enumerate(lines, start=1):
        if found := _marker(line):
            markers.append((line_number, *found))
    if not markers:
        label = {
            ".doc": "Word 文档",
            ".docx": "Word 文档",
            ".ppt": "PowerPoint 文档",
            ".pptx": "PowerPoint 文档",
            ".xls": "Excel 工作簿",
            ".xlsx": "Excel 工作簿",
            ".pdf": "PDF 文档",
        }.get(source_suffix.lower(), "源文档")
        return (
            SourceSpan(
                ProvenanceKind.DOCUMENT,
                label,
                None,
                1,
                max(1, len(lines)),
            ),
        )
    spans: list[SourceSpan] = []
    for index, (start, kind, label, ordinal, confidence) in enumerate(markers):
        end = markers[index + 1][0] - 1 if index + 1 < len(markers) else max(start, len(lines))
        spans.append(SourceSpan(kind, label, ordinal, start, end, confidence))
    return tuple(spans)


def source_label_for_line(spans: tuple[SourceSpan, ...], line: int) -> str:
    match = next((span for span in spans if span.start_line <= line <= span.end_line), None)
    return match.label if match else ""
