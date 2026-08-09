from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .markdown_cleaning import HEADING_PATTERN, IMAGE_PATTERN
from .markdown_splitting import estimate_tokens
from .markdown_types import QualityIssue, QualityReport


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
        issues.append(
            QualityIssue(
                "oversized_document",
                "warning",
                f"全文约 {estimated} 个 token，超过配置上限 {max_tokens}；建议使用拆分结果。",
            )
        )
    deductions = {"error": 25, "warning": 10, "info": 2}
    score = max(0, 100 - sum(deductions.get(issue.severity, 5) for issue in issues))
    return QualityReport(
        score=score,
        estimated_tokens=estimated,
        heading_count=sum(1 for line in text.splitlines() if HEADING_PATTERN.match(line)),
        image_count=len(IMAGE_PATTERN.findall(text)),
        issues=tuple(issues),
    )
