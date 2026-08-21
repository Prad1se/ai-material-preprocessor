from __future__ import annotations

from pathlib import Path

import pytest

from ai_material_preprocessor.application.executor_registry import (
    OperationExecutorRegistry,
    TaskExecutionResult,
    UnregisteredOperationError,
)
from ai_material_preprocessor.infrastructure.processes import CancellationToken
from ai_material_preprocessor.models import Job, Operation


class FakeOperationExecutor:
    def __init__(self, name: str, *, failure: Exception | None = None) -> None:
        self.name = name
        self.failure = failure
        self.calls: list[tuple[Job, int, CancellationToken | None]] = []

    def execute(
        self,
        job: Job,
        index: int,
        *,
        cancellation: CancellationToken | None = None,
        on_progress=None,
    ) -> TaskExecutionResult:
        self.calls.append((job, index, cancellation))
        if self.failure is not None:
            raise self.failure
        if on_progress:
            on_progress(50, self.name)
        return TaskExecutionResult(job.output_root / f"{self.name}.out")


def test_registry_routes_document_and_video_operations_to_registered_executors(
    tmp_path: Path,
) -> None:
    documents = FakeOperationExecutor("document")
    video = FakeOperationExecutor("video")
    registry = OperationExecutorRegistry()
    registry.register((Operation.TO_MARKDOWN, Operation.TO_PDF), documents)
    registry.register((Operation.COMPRESS_VIDEO, Operation.STANDARDIZE_MP4), video)

    document_job = Job(tmp_path / "lesson.docx", Operation.TO_MARKDOWN, tmp_path / "out")
    video_job = Job(tmp_path / "clip.mp4", Operation.STANDARDIZE_MP4, tmp_path / "out")

    assert registry.execute(document_job, 1).output.name == "document.out"
    assert registry.execute(video_job, 2).output.name == "video.out"
    assert documents.calls[0][:2] == (document_job, 1)
    assert video.calls[0][:2] == (video_job, 2)


def test_registry_supports_fake_injection_and_forwards_cancellation_and_progress(
    tmp_path: Path,
) -> None:
    fake = FakeOperationExecutor("fake")
    registry = OperationExecutorRegistry({Operation.EXTRACT_AUDIO: fake})
    token = CancellationToken()
    progress: list[tuple[int, str]] = []
    job = Job(tmp_path / "clip.mp4", Operation.EXTRACT_AUDIO, tmp_path / "out")

    registry.execute(job, 3, cancellation=token, on_progress=lambda *args: progress.append(args))

    assert fake.calls == [(job, 3, token)]
    assert progress == [(50, "fake")]


def test_registry_reports_unregistered_operation_clearly(tmp_path: Path) -> None:
    registry = OperationExecutorRegistry()
    job = Job(tmp_path / "clip.mp4", Operation.RENAME_VIDEO, tmp_path / "out")

    with pytest.raises(UnregisteredOperationError, match="RENAME_VIDEO"):
        registry.execute(job, 1)


def test_registry_propagates_executor_exceptions(tmp_path: Path) -> None:
    expected = RuntimeError("executor failed")
    registry = OperationExecutorRegistry(
        {Operation.TO_MARKDOWN: FakeOperationExecutor("document", failure=expected)}
    )

    with pytest.raises(RuntimeError, match="executor failed"):
        registry.execute(Job(tmp_path / "a.docx", Operation.TO_MARKDOWN, tmp_path), 1)
