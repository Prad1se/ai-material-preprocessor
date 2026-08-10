from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from .services.markdown_types import QualityReport


class PreviewRiskLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class SourceFilePreview:
    path: Path
    name: str
    suffix: str
    size_bytes: int
    modified_at: datetime


@dataclass(frozen=True)
class PreviewRisk:
    code: str
    level: PreviewRiskLevel
    message: str
    line: int | None = None
    source_label: str = ""


@dataclass(frozen=True)
class HeadingPreview:
    level: int
    title: str
    line: int


@dataclass(frozen=True)
class ChunkPreview:
    index: int
    title: str
    estimated_tokens: int


@dataclass(frozen=True)
class OCRPagePreview:
    label: str
    confidence: float
    low_confidence: bool


@dataclass(frozen=True)
class DocumentPreview:
    source: SourceFilePreview
    cleaned_markdown: str
    headings: tuple[HeadingPreview, ...]
    chunks: tuple[ChunkPreview, ...]
    quality: QualityReport
    ocr_pages: tuple[OCRPagePreview, ...]
    risks: tuple[PreviewRisk, ...]
    parameters: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class VideoPreview:
    source: SourceFilePreview
    captured_at: datetime
    location: str
    duration_seconds: float
    resolution: str
    codec: str
    camera: str
    frame_rate: float | None
    output_name: str
    estimated_size_min: int
    estimated_size_max: int
    risks: tuple[PreviewRisk, ...]
    parameters: tuple[tuple[str, str], ...]
