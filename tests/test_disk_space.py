from __future__ import annotations

from pathlib import Path

import pytest

from ai_material_preprocessor.errors import ErrorCode, UserFacingError
from ai_material_preprocessor.models import Job, Operation
from ai_material_preprocessor.services.disk_space import DiskSpacePreflight


def _job(tmp_path: Path, name: str, operation: Operation, size: int) -> Job:
    source = tmp_path / name
    source.write_bytes(b"x" * size)
    return Job(source, operation, tmp_path / "output with spaces")


def test_disk_preflight_estimates_all_jobs_and_reports_remaining_capacity(
    tmp_path: Path,
) -> None:
    jobs = [
        _job(tmp_path, "document.docx", Operation.TO_MARKDOWN, 1000),
        _job(tmp_path, "video.mp4", Operation.STANDARDIZE_MP4, 2000),
        _job(tmp_path, "organized.mov", Operation.ORGANIZE_VIDEO, 500),
    ]
    preflight = DiskSpacePreflight(free_space=lambda _path: 10_000)

    result = preflight.check(jobs, safety_margin_bytes=1000)

    assert result.required_bytes == 4500
    assert result.free_bytes == 10_000
    assert result.remaining_bytes == 4500


def test_disk_preflight_stops_before_processing_with_actionable_error(tmp_path: Path) -> None:
    job = _job(tmp_path, "large.mp4", Operation.STANDARDIZE_MP4, 2000)
    preflight = DiskSpacePreflight(free_space=lambda _path: 3000)

    with pytest.raises(UserFacingError) as raised:
        preflight.check([job], safety_margin_bytes=1000)

    assert raised.value.code is ErrorCode.FILE_SYSTEM
    assert "空间" in raised.value.user_message
    assert raised.value.retryable is True


def test_context_pack_preflight_sums_all_input_sources(tmp_path: Path) -> None:
    primary = _job(tmp_path, "primary.docx", Operation.DOCUMENT_CONTEXT_PACK, 1000)
    secondary = tmp_path / "secondary.pdf"
    secondary.write_bytes(b"x" * 2000)
    job = Job(
        primary.source,
        Operation.DOCUMENT_CONTEXT_PACK,
        primary.output_root,
        sources=(secondary,),
    )
    preflight = DiskSpacePreflight(free_space=lambda _path: 10_000)

    result = preflight.check([job], safety_margin_bytes=1000)

    assert result.required_bytes == 4500
