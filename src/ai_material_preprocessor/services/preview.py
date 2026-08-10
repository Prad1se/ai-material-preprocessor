from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

from ..models import Operation
from ..preview_models import (
    ChunkPreview,
    DocumentPreview,
    HeadingPreview,
    OCRPagePreview,
    PreviewRisk,
    PreviewRiskLevel,
    SourceFilePreview,
    VideoPreview,
)
from .document_enhancement import EnhancementOptions
from .markdown_cleaning import HEADING_PATTERN, clean_markdown
from .markdown_quality import check_quality, preserve_original_issues
from .markdown_splitting import split_markdown
from .metadata import MediaMetadata
from .naming import preview_video_rename

LOW_OCR_CONFIDENCE = 0.75
OCR_HEADING = re.compile(r"^###\s+(.+?)（平均置信度\s+([\d.]+)%）\s*$")


def _source_preview(source: Path) -> SourceFilePreview:
    stat = source.stat()
    return SourceFilePreview(
        path=source.resolve(),
        name=source.name,
        suffix=source.suffix.lower(),
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime).astimezone(),
    )


def _parameters(values: Mapping[str, object] | None) -> tuple[tuple[str, str], ...]:
    return tuple((str(key), str(value)) for key, value in (values or {}).items())


def _risk_level(value: str) -> PreviewRiskLevel:
    try:
        return PreviewRiskLevel(value)
    except ValueError:
        return PreviewRiskLevel.WARNING


def build_document_preview(
    source: Path,
    raw_markdown: str,
    *,
    base_dir: Path,
    options: EnhancementOptions,
    ocr_pages: Sequence[tuple[str, str, float]] = (),
    parameters: Mapping[str, object] | None = None,
) -> DocumentPreview:
    """Build a read-only preview from converted Markdown and optional OCR observations."""
    cleaned = clean_markdown(raw_markdown, source_suffix=source.suffix)
    quality = check_quality(
        cleaned,
        base_dir=base_dir,
        max_tokens=options.max_tokens,
        source_suffix=source.suffix,
    )
    original_quality = check_quality(
        raw_markdown,
        base_dir=base_dir,
        max_tokens=options.max_tokens,
        source_suffix=source.suffix,
    )
    quality = preserve_original_issues(quality, original_quality, codes={"heading_jump"})
    headings: list[HeadingPreview] = []
    for line_number, line in enumerate(cleaned.splitlines(), start=1):
        match = HEADING_PATTERN.match(line)
        if match:
            headings.append(HeadingPreview(len(match.group(1)), match.group(2), line_number))
    chunks = (
        split_markdown(
            cleaned,
            target_tokens=options.target_tokens,
            max_tokens=options.max_tokens,
            source_suffix=source.suffix,
        )
        if options.split_enabled
        else ()
    )
    ocr = tuple(
        OCRPagePreview(label, confidence, confidence < LOW_OCR_CONFIDENCE)
        for label, _text, confidence in ocr_pages
    )
    risks = [
        PreviewRisk(
            issue.code,
            _risk_level(issue.severity),
            issue.message,
            issue.line,
            issue.source_label,
        )
        for issue in quality.issues
    ]
    if re.search(r"(?m)^\s*\|.+\|\s*$", cleaned):
        risks.append(
            PreviewRisk(
                "table_layout",
                PreviewRiskLevel.INFO,
                "检测到 Markdown 表格；复杂合并单元格可能需要人工核对。",
            )
        )
    if re.search(r"(?s)\$\$.+?\$\$|(?<!\$)\$[^\n$]+\$", cleaned):
        risks.append(
            PreviewRisk(
                "formula",
                PreviewRiskLevel.INFO,
                "检测到公式；请核对源文档中的公式是否完整保留。",
            )
        )
    if re.search(r"(?m)^```", cleaned):
        risks.append(
            PreviewRisk(
                "code_block",
                PreviewRiskLevel.INFO,
                "检测到代码块；拆分时会将完整代码块作为一个结构单元。",
            )
        )
    if any(page.low_confidence for page in ocr):
        labels = "、".join(page.label for page in ocr if page.low_confidence)
        risks.append(
            PreviewRisk(
                "low_ocr_confidence",
                PreviewRiskLevel.WARNING,
                f"OCR 低置信度页面：{labels}。",
            )
        )
    return DocumentPreview(
        source=_source_preview(source),
        cleaned_markdown=cleaned,
        headings=tuple(headings),
        chunks=tuple(
            ChunkPreview(chunk.index, chunk.title, chunk.estimated_tokens) for chunk in chunks
        ),
        quality=quality,
        ocr_pages=ocr,
        risks=tuple(risks),
        parameters=_parameters(parameters),
    )


def ocr_pages_from_markdown(markdown: str) -> tuple[tuple[str, str, float], ...]:
    pages: list[tuple[str, str, float]] = []
    for line in markdown.splitlines():
        if match := OCR_HEADING.match(line):
            pages.append((match.group(1), "", float(match.group(2)) / 100))
    return tuple(pages)


def document_preview_to_dict(preview: DocumentPreview) -> dict[str, object]:
    return {
        "source": preview.source.name,
        **preview.quality.to_dict(),
        "source_size": preview.source.size_bytes,
        "source_suffix": preview.source.suffix,
        "cleaned_preview": preview.cleaned_markdown[:12_000],
        "headings": [asdict(item) for item in preview.headings],
        "chunks": [asdict(item) for item in preview.chunks],
        "ocr_pages": [asdict(item) for item in preview.ocr_pages],
        "risks": [
            {
                "code": item.code,
                "level": item.level.value,
                "message": item.message,
                "line": item.line,
                "source_label": item.source_label,
            }
            for item in preview.risks
        ],
        "parameters": dict(preview.parameters),
    }


def _predicted_video_name(
    source: Path, operation: Operation, parameters: Mapping[str, object]
) -> str:
    if operation is Operation.COMPRESS_VIDEO:
        return f"{source.stem}_compressed.mp4"
    if operation is Operation.EXTRACT_AUDIO:
        extension = (
            ".wav" if str(parameters.get("audio_format", "mp3")).lower() == "wav" else ".mp3"
        )
        return f"{source.stem}{extension}"
    if operation is Operation.STANDARDIZE_MP4:
        return f"{source.stem}_standard.mp4"
    if operation is Operation.KEYFRAMES_CONTACT_SHEET:
        return f"{source.stem}_关键帧包/contact-sheet.jpg"
    return source.name


def _audio_bytes(duration: float, audio_format: str, bitrate: str) -> tuple[int, int]:
    if duration <= 0:
        return (0, 0)
    if audio_format.lower() == "wav":
        estimate = round(duration * 48_000 * 2 * 2)
    else:
        match = re.search(r"\d+", bitrate)
        bits_per_second = (int(match.group()) if match else 192) * 1000
        estimate = round(duration * bits_per_second / 8)
    return (round(estimate * 0.9), round(estimate * 1.1))


def _video_size_range(
    source_size: int,
    metadata: MediaMetadata,
    operation: Operation,
    parameters: Mapping[str, object],
) -> tuple[int, int]:
    if operation is Operation.EXTRACT_AUDIO:
        return _audio_bytes(
            float(metadata.duration_seconds or 0),
            str(parameters.get("audio_format", "mp3")),
            str(parameters.get("audio_bitrate", "192k")),
        )
    if operation is Operation.COMPRESS_VIDEO:
        crf = int(str(parameters.get("compression_crf", 23)))
        center = max(0.12, min(1.1, 0.62 - (crf - 23) * 0.035))
        return (round(source_size * center * 0.65), round(source_size * center * 1.35))
    if operation is Operation.STANDARDIZE_MP4:
        return (round(source_size * 0.5), round(source_size * 1.5))
    if operation is Operation.KEYFRAMES_CONTACT_SHEET:
        maximum = max(1, int(str(parameters.get("max_keyframes", 24))))
        return (150_000, maximum * 1_000_000)
    return (source_size, source_size)


def build_video_preview(
    source: Path,
    metadata: MediaMetadata,
    operation: Operation,
    output_root: Path,
    *,
    parameters: Mapping[str, object] | None = None,
    index: int = 1,
    manual_location: str = "",
) -> VideoPreview:
    values = parameters or {}
    if operation is Operation.RENAME_VIDEO:
        rename = preview_video_rename(
            source,
            output_root,
            metadata,
            str(values.get("rename_template", "{date}_{time}_{location}_{index}")),
            index,
            manual_location,
        )
        output_name = rename.output.name
    else:
        output_name = _predicted_video_name(source, operation, values)
    risks: list[PreviewRisk] = []
    if operation in {Operation.COMPRESS_VIDEO, Operation.STANDARDIZE_MP4}:
        risks.append(
            PreviewRisk(
                "lossy_video",
                PreviewRiskLevel.WARNING,
                "视频将重新编码，可能产生不可逆的画质损失。",
            )
        )
        if metadata.codec.lower() not in {"h264", "avc", "avc1"}:
            risks.append(
                PreviewRisk(
                    "codec_change",
                    PreviewRiskLevel.INFO,
                    f"视频编码将从 {metadata.codec or '未知'} 调整为 H.264。",
                )
            )
    if operation is Operation.EXTRACT_AUDIO and str(values.get("audio_format", "mp3")) == "mp3":
        risks.append(
            PreviewRisk(
                "lossy_audio",
                PreviewRiskLevel.WARNING,
                "MP3 为有损输出，不会提升源音频质量。",
            )
        )
    source_info = _source_preview(source)
    size_min, size_max = _video_size_range(source_info.size_bytes, metadata, operation, values)
    return VideoPreview(
        source=source_info,
        captured_at=metadata.captured_at,
        location=metadata.effective_location(manual_location),
        duration_seconds=float(metadata.duration_seconds or 0),
        resolution=metadata.resolution,
        codec=metadata.codec,
        camera=metadata.camera,
        frame_rate=metadata.frame_rate,
        output_name=output_name,
        estimated_size_min=size_min,
        estimated_size_max=size_max,
        risks=tuple(risks),
        parameters=_parameters(values),
    )


def _collision_name(name: str, reserved: set[str]) -> tuple[str, bool]:
    candidate = Path(name)
    collision = candidate.name.casefold() in reserved
    counter = 2
    while candidate.name.casefold() in reserved:
        candidate = candidate.with_name(f"{Path(name).stem}_{counter}{Path(name).suffix}")
        counter += 1
    reserved.add(candidate.name.casefold())
    return candidate.name, collision


def build_batch_rename_preview(
    sources: Sequence[Path],
    metadata: Sequence[MediaMetadata],
    output_root: Path,
    *,
    template: str,
    manual_location: str = "",
) -> tuple[VideoPreview, ...]:
    if len(sources) != len(metadata):
        raise ValueError("视频文件和元数据数量不一致。")
    reserved = (
        {path.name.casefold() for path in output_root.iterdir()} if output_root.is_dir() else set()
    )
    results: list[VideoPreview] = []
    for index, (source, values) in enumerate(zip(sources, metadata, strict=True), start=1):
        preview = build_video_preview(
            source,
            values,
            Operation.RENAME_VIDEO,
            output_root,
            parameters={"rename_template": template},
            index=index,
            manual_location=manual_location,
        )
        output_name, planned_collision = _collision_name(preview.output_name, reserved)
        risks = preview.risks
        if planned_collision:
            risks += (
                PreviewRisk(
                    "planned_name_collision",
                    PreviewRiskLevel.WARNING,
                    "批次中存在重名，预览已追加编号；原文件未修改。",
                ),
            )
        results.append(replace(preview, output_name=output_name, risks=risks))
    return tuple(results)


def completed_contact_sheet(output: Path) -> Path | None:
    return output if output.is_file() and output.name.casefold() == "contact-sheet.jpg" else None
