from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_material_preprocessor.application.default_registry import build_default_executor_registry
from ai_material_preprocessor.application.task_runner import _quality_summary
from ai_material_preprocessor.apps.documents.policy import DOCUMENT_OPERATIONS
from ai_material_preprocessor.apps.video.policy import LEGACY_VIDEO_OPERATIONS, VIDEO_OPERATIONS
from ai_material_preprocessor.apps.video.workspace_controller import VideoWorkspaceController
from ai_material_preprocessor.infrastructure.processes import CancellationToken
from ai_material_preprocessor.models import Job, Operation, QueuedTask, ToolStatus
from ai_material_preprocessor.services.task_repository import PersistentTaskQueue
from ai_material_preprocessor.services.video_ai_pack import VideoAIPackResult


class FakeDocumentService:
    def convert(self, job, **_kwargs):
        return job.output_root / "document.out", ()


class FakeLegacyVideoService:
    def __init__(self) -> None:
        self.calls = []

    def convert(self, job, index, **_kwargs):
        self.calls.append((job, index))
        return job.output_root / "legacy.out"


class FakePackService:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls = []

    def create_pack(self, job, index=1, *, cancellation=None, on_progress=None):
        self.calls.append((job, index, cancellation))
        if self.failure:
            raise self.failure
        if on_progress:
            on_progress(50, "pack")
        return VideoAIPackResult(
            job.output_root / "Video-AI-Pack",
            {"video_ai_pack_version": 1, "source_count": len(job.input_sources)},
        )


def _tools() -> dict[str, ToolStatus]:
    return {"ffmpeg": ToolStatus("ffmpeg", "ffmpeg.exe")}


def test_operation_policy_and_default_registry_route_pack_separately(tmp_path: Path) -> None:
    legacy = FakeLegacyVideoService()
    pack = FakePackService()
    registry = build_default_executor_registry(FakeDocumentService(), legacy, pack)
    token = CancellationToken()
    progress = []
    pack_job = Job(tmp_path / "a.mp4", Operation.VIDEO_AI_PACK, tmp_path / "out")

    result = registry.execute(
        pack_job,
        4,
        cancellation=token,
        on_progress=lambda *args: progress.append(args),
    )
    legacy_job = Job(tmp_path / "b.mp4", Operation.STANDARDIZE_MP4, tmp_path / "out")
    legacy_result = registry.execute(legacy_job, 2)

    assert Operation.VIDEO_AI_PACK in VIDEO_OPERATIONS
    assert Operation.VIDEO_AI_PACK not in LEGACY_VIDEO_OPERATIONS
    assert Operation.VIDEO_AI_PACK not in DOCUMENT_OPERATIONS
    assert result.output.name == "Video-AI-Pack"
    assert result.quality_reports[0]["video_ai_pack_version"] == 1
    assert pack.calls == [(pack_job, 4, token)]
    assert progress == [(50, "pack")]
    assert legacy_result.output.name == "legacy.out"
    assert legacy.calls == [(legacy_job, 2)]


def test_existing_operation_names_remain_stable() -> None:
    assert [
        operation.name for operation in Operation if operation is not Operation.VIDEO_AI_PACK
    ] == [
        "TO_MARKDOWN",
        "TO_PDF",
        "COMPRESS_VIDEO",
        "EXTRACT_AUDIO",
        "STANDARDIZE_MP4",
        "KEYFRAMES_CONTACT_SHEET",
        "RENAME_VIDEO",
        "ORGANIZE_VIDEO",
        "DOCUMENT_CONTEXT_PACK",
    ]


def test_pack_executor_propagates_exception(tmp_path: Path) -> None:
    registry = build_default_executor_registry(
        FakeDocumentService(),
        FakeLegacyVideoService(),
        FakePackService(failure=RuntimeError("pack failed")),
    )
    with pytest.raises(RuntimeError, match="pack failed"):
        registry.execute(Job(tmp_path / "a.mp4", Operation.VIDEO_AI_PACK, tmp_path), 1)


def test_controller_creates_one_multi_source_pack_job_and_keeps_old_video_jobs(
    tmp_path: Path,
) -> None:
    controller = VideoWorkspaceController(_tools())
    sources = [tmp_path / "b.mp4", tmp_path / "a.mp4"]

    pack_jobs = controller.create_jobs(
        sources,
        Operation.VIDEO_AI_PACK,
        lambda _source: tmp_path / "out",
        include_audio=False,
        include_proxy=True,
        proxy_crf=30,
        scene_threshold=0.2,
        max_keyframes=12,
    )
    old_jobs = controller.create_jobs(
        sources,
        Operation.STANDARDIZE_MP4,
        lambda source: source.parent / "old",
    )

    assert len(pack_jobs) == 1
    assert pack_jobs[0].input_sources == tuple(sources)
    assert pack_jobs[0].video_ai_pack_include_audio is False
    assert pack_jobs[0].video_ai_pack_include_proxy is True
    assert pack_jobs[0].video_ai_pack_proxy_crf == 30
    assert pack_jobs[0].video_ai_pack_scene_threshold == 0.2
    assert pack_jobs[0].video_ai_pack_max_keyframes == 12
    assert [job.source for job in old_jobs] == sources
    assert all(job.sources == () for job in old_jobs)


def test_pack_job_queue_round_trip_and_legacy_defaults(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "tasks.json")
    primary = tmp_path / "one.mp4"
    secondary = tmp_path / "two.mp4"
    now = datetime(2026, 8, 24, tzinfo=UTC)
    task = QueuedTask(
        "pack-task",
        Job(
            primary,
            Operation.VIDEO_AI_PACK,
            tmp_path / "out",
            sources=(primary, secondary),
            video_ai_pack_include_audio=False,
            video_ai_pack_include_proxy=True,
            video_ai_pack_proxy_crf=31,
            video_ai_pack_scene_threshold=0.45,
            video_ai_pack_max_keyframes=16,
        ),
        created_at=now,
        updated_at=now,
    )
    queue.save([task])
    payload = json.loads(queue.path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert queue.load() == [task]
    for key in (
        "video_ai_pack_include_audio",
        "video_ai_pack_include_proxy",
        "video_ai_pack_proxy_crf",
        "video_ai_pack_scene_threshold",
        "video_ai_pack_max_keyframes",
    ):
        payload["tasks"][0].pop(key)
    queue.path.write_text(json.dumps(payload), encoding="utf-8")
    restored = queue.load()[0].job
    assert restored.operation is Operation.VIDEO_AI_PACK
    assert restored.video_ai_pack_include_audio is None
    assert restored.video_ai_pack_include_proxy is None
    assert restored.video_ai_pack_proxy_crf is None
    assert restored.video_ai_pack_scene_threshold is None
    assert restored.video_ai_pack_max_keyframes is None


def test_video_ai_pack_quality_summary_is_additive() -> None:
    integrity = {"ok": True, "missing_artifacts": []}
    warnings = [{"code": "audio_unavailable"}]
    summary = _quality_summary(
        (
            {
                "video_ai_pack_version": 1,
                "source_count": 2,
                "frame_count": 5,
                "audio_count": 1,
                "proxy_count": 0,
                "warnings": warnings,
                "integrity": integrity,
                "private_path": "D:/private",
            },
        )
    )
    assert summary == {
        "video_ai_pack_version": 1,
        "source_count": 2,
        "frame_count": 5,
        "audio_count": 1,
        "proxy_count": 0,
        "warnings": warnings,
        "integrity": integrity,
    }
