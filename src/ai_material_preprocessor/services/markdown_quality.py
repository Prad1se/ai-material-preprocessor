from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .document_provenance import (
    ProvenanceKind,
    extract_provenance,
    source_label_for_line,
)
from .markdown_cleaning import HEADING_PATTERN, IMAGE_PATTERN
from .markdown_splitting import estimate_tokens
from .markdown_types import QualityIssue, QualityReport


def preserve_original_issues(
    cleaned: QualityReport,
    original: QualityReport,
    *,
    codes: set[str],
) -> QualityReport:
    existing = {(item.code, item.line, item.source_label) for item in cleaned.issues}
    additions = tuple(
        item
        for item in original.issues
        if item.code in codes and (item.code, item.line, item.source_label) not in existing
    )
    if not additions:
        return cleaned
    deductions = {"error": 25, "warning": 10, "info": 2}
    return QualityReport(
        score=max(
            0,
            cleaned.score - sum(deductions.get(issue.severity, 5) for issue in additions),
        ),
        estimated_tokens=cleaned.estimated_tokens,
        heading_count=cleaned.heading_count,
        image_count=cleaned.image_count,
        issues=cleaned.issues + additions,
    )


def _table_cell_count(line: str) -> int:
    return len([cell for cell in line.strip().strip("|").split("|")])


def _meaningful_source_content(lines: list[str]) -> bool:
    return any(
        line.strip() and line.strip() != "---" and not line.lstrip().startswith(("<!--", "#"))
        for line in lines
    )


def check_quality(
    text: str,
    *,
    base_dir: Path,
    max_tokens: int,
    source_suffix: str = "",
) -> QualityReport:
    issues: list[QualityIssue] = []
    lines = text.splitlines()
    spans = extract_provenance(text, source_suffix=source_suffix)

    def add(code: str, severity: str, message: str, line: int | None = None) -> None:
        issues.append(
            QualityIssue(
                code,
                severity,
                message,
                line,
                source_label_for_line(spans, line) if line is not None else "",
            )
        )

    stripped = text.strip()
    estimated = estimate_tokens(text)
    if not stripped:
        add("empty_document", "error", "转换结果为空。")
    elif estimated < 10:
        add("very_short", "warning", "内容很少，请核对转换是否完整。")

    fence_lines = [
        line_number
        for line_number, line in enumerate(lines, start=1)
        if re.match(r"^\s*(`{3,}|~{3,})", line)
    ]
    if len(fence_lines) % 2:
        add("unclosed_code_fence", "error", "存在未闭合的代码块。", fence_lines[-1])

    previous = 0
    for line_number, line in enumerate(lines, start=1):
        heading = HEADING_PATTERN.match(line)
        if heading:
            level = len(heading.group(1))
            if previous and level > previous + 1:
                add("heading_jump", "warning", "仍存在跳级标题。", line_number)
            previous = level

    for match in IMAGE_PATTERN.finditer(text):
        raw = match.group(2).strip().strip("<>").split(maxsplit=1)[0]
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https", "data"}:
            candidate = Path(raw.replace("/", str(Path("/"))))
            if not candidate.is_absolute():
                candidate = base_dir / candidate
            if not candidate.is_file():
                line_number = text.count("\n", 0, match.start()) + 1
                add(
                    "missing_image",
                    "warning",
                    f"图片路径无效：{raw}",
                    line_number,
                )

    table_start = 0
    expected_columns = 0
    for line_number, line in [*enumerate(lines, start=1), (len(lines) + 1, "")]:
        if line.strip().startswith("|") and line.strip().endswith("|"):
            columns = _table_cell_count(line)
            if table_start == 0:
                table_start = line_number
                expected_columns = columns
            elif columns != expected_columns:
                add(
                    "malformed_table",
                    "warning",
                    f"表格列数不一致：期望 {expected_columns} 列，当前 {columns} 列。",
                    line_number,
                )
            continue
        table_start = 0
        expected_columns = 0

    for span in spans:
        if span.source_type not in {ProvenanceKind.PAGE, ProvenanceKind.SLIDE}:
            continue
        section = lines[span.start_line - 1 : span.end_line]
        if not _meaningful_source_content(section):
            add(
                "empty_source_section",
                "warning",
                f"{span.label} 没有提取到正文内容。",
                span.start_line,
            )

    if source_suffix.lower() in {".doc", ".docx", ".ppt", ".pptx"} and re.search(
        r"\[(?:Equation|公式)\]|\bOMML\b|�", text, re.IGNORECASE
    ):
        formula_match = re.search(r"\[(?:Equation|公式)\]|\bOMML\b|�", text, re.IGNORECASE)
        formula_line_number = (
            text.count("\n", 0, formula_match.start()) + 1 if formula_match else None
        )
        add(
            "possible_formula_loss",
            "warning",
            "检测到公式占位或异常字符，源公式可能没有完整保留。",
            formula_line_number,
        )

    if estimated > max_tokens:
        add(
            "oversized_document",
            "warning",
            f"全文约 {estimated} 个 token，超过配置上限 {max_tokens}；建议使用拆分结果。",
        )
    deductions = {"error": 25, "warning": 10, "info": 2}
    score = max(0, 100 - sum(deductions.get(issue.severity, 5) for issue in issues))
    return QualityReport(
        score=score,
        estimated_tokens=estimated,
        heading_count=sum(1 for line in lines if HEADING_PATTERN.match(line)),
        image_count=len(IMAGE_PATTERN.findall(text)),
        issues=tuple(issues),
    )
