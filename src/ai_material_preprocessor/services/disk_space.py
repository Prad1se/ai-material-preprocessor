from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..errors import ErrorCode, UserFacingError
from ..models import Job, Operation


@dataclass(frozen=True)
class DiskSpaceAssessment:
    required_bytes: int
    free_bytes: int
    safety_margin_bytes: int

    @property
    def remaining_bytes(self) -> int:
        return self.free_bytes - self.required_bytes - self.safety_margin_bytes


def _nearest_existing(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


class DiskSpacePreflight:
    """Conservative output-size estimates; never writes during inspection."""

    FACTORS = {
        Operation.TO_MARKDOWN: 1.5,
        Operation.TO_PDF: 1.5,
        Operation.COMPRESS_VIDEO: 0.75,
        Operation.EXTRACT_AUDIO: 0.5,
        Operation.STANDARDIZE_MP4: 1.25,
        Operation.KEYFRAMES_CONTACT_SHEET: 0.5,
        Operation.RENAME_VIDEO: 1.0,
    }

    def __init__(self, *, free_space: Callable[[Path], int] | None = None) -> None:
        self._free_space = free_space or (lambda path: shutil.disk_usage(path).free)

    def estimate(self, job: Job) -> int:
        try:
            source_size = job.source.stat().st_size
        except OSError as exc:
            raise UserFacingError(
                ErrorCode.FILE_SYSTEM,
                f"无法读取“{job.source.name}”的大小，请检查文件是否仍然存在。",
                technical_detail=f"{type(exc).__name__}: {exc}",
                retryable=True,
            ) from exc
        return max(1, round(source_size * self.FACTORS[job.operation]))

    def check(
        self,
        jobs: list[Job],
        *,
        safety_margin_bytes: int = 512 * 1024 * 1024,
    ) -> DiskSpaceAssessment:
        required = sum(self.estimate(job) for job in jobs)
        roots = {_nearest_existing(job.output_root) for job in jobs}
        free = min((self._free_space(root) for root in roots), default=0)
        assessment = DiskSpaceAssessment(required, free, max(0, safety_margin_bytes))
        if assessment.remaining_bytes < 0:
            shortage = -assessment.remaining_bytes
            raise UserFacingError(
                ErrorCode.FILE_SYSTEM,
                "输出目录可用空间不足，请清理空间或选择其他目录后重试。",
                technical_detail=(
                    f"required={required}; free={free}; margin={safety_margin_bytes}; "
                    f"shortage={shortage}"
                ),
                retryable=True,
            )
        return assessment
