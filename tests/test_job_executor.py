from __future__ import annotations

from pathlib import Path

from ai_material_preprocessor.errors import ErrorCode, UserFacingError
from ai_material_preprocessor.models import Job, Operation, ToolStatus
from ai_material_preprocessor.services.job_executor import JobExecutor


class FakeDocumentService:
    def __init__(self) -> None:
        self.calls: list[tuple[Operation, Path]] = []

    def convert(self, job: Job) -> tuple[Path, list[dict]]:
        self.calls.append((job.operation, job.source))
        if "broken" in job.source.name:
            raise UserFacingError(
                ErrorCode.CONVERSION_FAILED,
                "文档转换失败，请确认文件没有损坏。",
                technical_detail="fixture failure",
                retryable=True,
            )
        output = job.output_root / f"{job.source.stem}.md"
        return output, [{"source": job.source.name, "score": 100}]


class FakeVideoService:
    def convert(self, job: Job, index: int) -> Path:
        return job.output_root / f"{index:03d}-{job.source.name}"


def tools() -> dict[str, ToolStatus]:
    return {
        name: ToolStatus(name, None)
        for name in (
            "markitdown",
            "ffmpeg",
            "ffprobe",
            "exiftool",
            "libreoffice",
            "winword",
            "powerpoint",
            "rapidocr",
        )
    }


def test_batch_executor_isolates_failures_and_returns_typed_records(tmp_path: Path) -> None:
    jobs = [
        Job(tmp_path / "one.docx", Operation.TO_MARKDOWN, tmp_path / "out"),
        Job(tmp_path / "broken.docx", Operation.TO_MARKDOWN, tmp_path / "out"),
        Job(tmp_path / "two.docx", Operation.TO_MARKDOWN, tmp_path / "out"),
    ]
    documents = FakeDocumentService()
    executor = JobExecutor(
        tools=tools(),
        config={},
        document_service=documents,
        video_service=FakeVideoService(),
    )

    result = executor.execute_batch(jobs)

    assert [path.name for path in result.outputs] == ["one.md", "two.md"]
    assert len(result.failures) == 1
    assert result.failures[0].source.name == "broken.docx"
    assert result.failures[0].error.code is ErrorCode.CONVERSION_FAILED
    assert [record.status for record in result.records] == ["success", "failed", "success"]
    assert len(result.quality_reports) == 2


def test_batch_executor_reports_progress_for_each_item(tmp_path: Path) -> None:
    jobs = [
        Job(tmp_path / "one.mp4", Operation.STANDARDIZE_MP4, tmp_path / "out"),
        Job(tmp_path / "two.mp4", Operation.STANDARDIZE_MP4, tmp_path / "out"),
    ]
    progress: list[tuple[int, int, str]] = []
    executor = JobExecutor(
        tools=tools(),
        config={},
        document_service=FakeDocumentService(),
        video_service=FakeVideoService(),
    )

    result = executor.execute_batch(
        jobs,
        on_progress=lambda completed, total, message: progress.append((completed, total, message)),
    )

    assert len(result.outputs) == 2
    assert progress[0][:2] == (0, 2)
    assert progress[-1][:2] == (2, 2)
    assert "two.mp4" in progress[-1][2]
