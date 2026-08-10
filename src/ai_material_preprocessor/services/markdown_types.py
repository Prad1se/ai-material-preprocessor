from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class QualityIssue:
    code: str
    severity: str
    message: str
    line: int | None = None
    source_label: str = ""


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
    source_labels: tuple[str, ...] = ()
