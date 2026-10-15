from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from ai_material_preprocessor.converters.video import KeyframeArtifacts
from ai_material_preprocessor.errors import ErrorCode, UserFacingError
from ai_material_preprocessor.infrastructure.processes import CancellationToken
from ai_material_preprocessor.models import Job, Operation, ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.services.metadata import MediaMetadata
from ai_material_preprocessor.services.video_ai_pack import (
    VideoAIPackService,
    VideoFrame,
    VideoTimelineEntry,
    validate_video_ai_pack,
    validate_written_video_ai_pack_manifest,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metadata(source: Path, *_args, **_kwargs) -> MediaMetadata:
    return MediaMetadata(
        datetime(2026, 8, 24, 9, 30, tzinfo=UTC),
        None,
        None,
        "深圳",
        "ffprobe",
        duration_seconds=12.5,
        width=1920,
        height=1080,
        codec="h264",
        make="CameraCo",
        model="C1",
        frame_rate=25.0,
        capture_time_source="creation_time",
    )


def _keyframes(
    source: Path,
    frames_dir: Path,
    contact_sheet: Path,
    *_args,
    **_kwargs,
) -> KeyframeArtifacts:
    del source
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for index in range(1, 3):
        frame = frames_dir / f"frame-{index:03d}.jpg"
        Image.new("RGB", (64, 36), "white").save(frame)
        frames.append(frame)
    Image.new("RGB", (128, 72), "white").save(contact_sheet)
    return KeyframeArtifacts(tuple(frames), (1.25, 8.5), contact_sheet, False)


def _audio(
    source: Path,
    output_root: Path,
    _ffmpeg: str | None,
    _audio_format: str,
    _bitrate: str,
    **_kwargs,
) -> Path:
    del source
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root / "audio.wav"
    output.write_bytes(b"RIFF-fake")
    return output


def _service(**overrides) -> VideoAIPackService:
    dependencies = {
        "metadata_reader": _metadata,
        "keyframe_generator": _keyframes,
        "audio_probe": lambda *_args, **_kwargs: True,
        "audio_extractor": _audio,
        "proxy_generator": lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("proxy should not run")
        ),
    }
    dependencies.update(overrides)
    return VideoAIPackService(
        {
            "ffmpeg": ToolStatus("ffmpeg", "ffmpeg.exe"),
            "ffprobe": ToolStatus("ffprobe", "ffprobe.exe"),
            "exiftool": ToolStatus("exiftool", None),
        },
        deepcopy(DEFAULT_CONFIG),
        **dependencies,
    )


def test_builds_one_privacy_safe_pack_for_multiple_sources_in_input_order(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "甲"
    second_dir = tmp_path / "乙"
    first_dir.mkdir()
    second_dir.mkdir()
    sources = (first_dir / "课程录像.mp4", second_dir / "课程录像.mp4")
    for index, source in enumerate(sources, start=1):
        source.write_bytes(f"source-{index}".encode())
    before = {source: _sha256(source) for source in sources}
    progress: list[str] = []

    result = _service().create_pack(
        Job(
            sources[0],
            Operation.VIDEO_AI_PACK,
            tmp_path / "output",
            sources=sources,
            video_ai_pack_include_audio=True,
            video_ai_pack_include_proxy=False,
            video_ai_pack_scene_threshold=0.3,
            video_ai_pack_max_keyframes=24,
        ),
        on_progress=lambda _value, message: progress.append(message),
    )

    assert result.output.name == "Video-AI-Pack"
    manifest = json.loads((result.output / "manifest.json").read_text(encoding="utf-8"))
    timeline = json.loads((result.output / "timeline.json").read_text(encoding="utf-8"))
    metadata = json.loads((result.output / "metadata.json").read_text(encoding="utf-8"))
    assert manifest["package_type"] == "video_ai_pack"
    assert manifest["video_ai_pack_version"] == 1
    assert [item["source_id"] for item in manifest["sources"]] == ["video-001", "video-002"]
    assert [item["display_name"] for item in manifest["sources"]] == [
        "课程录像.mp4",
        "课程录像.mp4",
    ]
    assert manifest["integrity"]["ok"] is True
    assert result.report["source_count"] == 2
    assert result.report["frame_count"] == 4
    assert result.report["audio_count"] == 2
    assert result.report["proxy_count"] == 0
    assert [item["frame_id"] for item in timeline["entries"]] == [
        "video-001-frame-001",
        "video-001-frame-002",
        "video-002-frame-001",
        "video-002-frame-002",
    ]
    assert timeline["entries"][0]["timestamp_label"] == "00:00:01.250"
    assert metadata["sources"][0]["resolution"] == "1920x1080"
    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in result.output.rglob("*")
        if path.is_file() and path.suffix in {".json", ".md"}
    )
    assert str(tmp_path) not in public_text
    assert all(_sha256(source) == before[source] for source in sources)
    assert "正在验证资料包" in progress
    assert not any(
        path.name.startswith(".Video-AI-Pack.tmp") for path in result.output.parent.iterdir()
    )


def test_null_timestamp_and_no_audio_stream_are_explicit(tmp_path: Path) -> None:
    source = tmp_path / "silent.mp4"
    source.write_bytes(b"silent")

    def frames_with_unknown_timestamp(*args, **kwargs):
        artifacts = _keyframes(*args, **kwargs)
        return KeyframeArtifacts(artifacts.frames, (), artifacts.contact_sheet, False)

    result = _service(
        keyframe_generator=frames_with_unknown_timestamp,
        audio_probe=lambda *_args, **_kwargs: False,
    ).create_pack(
        Job(
            source,
            Operation.VIDEO_AI_PACK,
            tmp_path / "out",
            video_ai_pack_include_audio=True,
        )
    )

    timeline = json.loads((result.output / "timeline.json").read_text(encoding="utf-8"))
    source_manifest = json.loads(
        (result.output / "sources" / "video-001" / "metadata.json").read_text(encoding="utf-8")
    )
    assert timeline["entries"][0]["timestamp_seconds"] is None
    assert timeline["entries"][0]["timestamp_label"] is None
    assert source_manifest["audio"]["status"] == "unavailable"
    assert source_manifest["warnings"][0]["code"] == "audio_unavailable"
    assert result.report["audio_count"] == 0
    assert any(item["code"] == "audio_unavailable" for item in result.report["warnings"])


def test_optional_failures_warn_but_core_pack_remains_complete(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"clip")

    def fail_audio(*_args, **_kwargs):
        raise RuntimeError("recoverable audio failure")

    def fail_proxy(*_args, **_kwargs):
        raise RuntimeError("recoverable proxy failure")

    result = _service(audio_extractor=fail_audio, proxy_generator=fail_proxy).create_pack(
        Job(
            source,
            Operation.VIDEO_AI_PACK,
            tmp_path / "out",
            video_ai_pack_include_audio=True,
            video_ai_pack_include_proxy=True,
        )
    )

    assert result.report["integrity"]["ok"] is True
    assert {item["code"] for item in result.report["warnings"]} == {
        "audio_extraction_failed",
        "proxy_generation_failed",
    }
    manifest = json.loads((result.output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sources"][0]["audio"]["status"] == "failed"
    assert manifest["sources"][0]["proxy"]["status"] == "failed"


def test_collision_safe_output_and_cancellation_cleanup(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"clip")
    output_root = tmp_path / "out"
    (output_root / "Video-AI-Pack").mkdir(parents=True)

    result = _service().create_pack(
        Job(source, Operation.VIDEO_AI_PACK, output_root, video_ai_pack_include_audio=False)
    )
    assert result.output.name == "Video-AI-Pack_2"

    token = CancellationToken()

    def cancel_during_frames(*args, **kwargs):
        token.cancel()
        return _keyframes(*args, **kwargs)

    with pytest.raises(Exception, match="任务已取消"):
        _service(keyframe_generator=cancel_during_frames).create_pack(
            Job(
                source,
                Operation.VIDEO_AI_PACK,
                output_root,
                video_ai_pack_include_audio=False,
            ),
            cancellation=token,
        )

    assert sorted(path.name for path in output_root.iterdir()) == [
        "Video-AI-Pack",
        "Video-AI-Pack_2",
    ]


def test_integrity_detects_missing_artifact_duplicate_frame_id_and_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "pack"
    root.mkdir()
    existing = root / "sources" / "video-001" / "frames" / "frame-001.jpg"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"frame")
    relative = existing.relative_to(root).as_posix()
    frames = (
        VideoFrame("video-001", "video-001-frame-001", relative, 0.0),
        VideoFrame("video-001", "video-001-frame-001", "missing.jpg", None),
    )
    timeline = (
        VideoTimelineEntry("video-001", "video-001-frame-001", 0.0, "00:00:00.000", relative),
    )

    integrity = validate_video_ai_pack(
        root,
        source_ids=("video-001",),
        frames=frames,
        timeline=timeline,
        artifacts=(relative, "missing.jpg", "../escape.jpg"),
        statuses=(),
        source_hashes_unchanged=True,
    )

    assert integrity.ok is False
    assert integrity.duplicate_ids == ("video-001-frame-001",)
    assert integrity.missing_artifacts == ("missing.jpg",)
    assert integrity.path_violations == ("../escape.jpg",)
    assert integrity.timeline_order_preserved is False


def test_integrity_detects_timeline_payload_and_status_coverage_mismatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "pack"
    frame_path = root / "sources/video-001/frames/frame-001.jpg"
    frame_path.parent.mkdir(parents=True)
    frame_path.write_bytes(b"frame")
    relative = frame_path.relative_to(root).as_posix()
    frame = VideoFrame("video-001", "video-001-frame-001", relative, 1.5)

    integrity = validate_video_ai_pack(
        root,
        source_ids=("video-001",),
        frames=(frame,),
        timeline=(
            VideoTimelineEntry(
                "video-001",
                "video-001-frame-001",
                9.0,
                "00:00:09.000",
                "wrong.jpg",
            ),
        ),
        artifacts=(relative,),
        statuses=(
            {
                "source_id": "video-001",
                "artifact_type": "audio",
                "requested": False,
                "status": "not_requested",
                "path": None,
            },
        ),
        source_hashes_unchanged=True,
    )

    assert integrity.timeline_order_preserved is False
    assert integrity.status_consistent is False
    assert integrity.ok is False


def test_external_audio_output_is_rejected_without_moving_or_publishing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"clip")
    external = tmp_path / "external.wav"
    external.write_bytes(b"external-audio")
    output_root = tmp_path / "out"

    with pytest.raises(UserFacingError) as caught:
        _service(audio_extractor=lambda *_args, **_kwargs: external).create_pack(
            Job(source, Operation.VIDEO_AI_PACK, output_root)
        )

    assert caught.value.code is ErrorCode.INTEGRITY_FAILED
    assert external.read_bytes() == b"external-audio"
    assert not (output_root / "Video-AI-Pack").exists()
    assert not any(path.name.startswith(".Video-AI-Pack.tmp") for path in output_root.iterdir())


@pytest.mark.parametrize(
    "failing_dependency", ["audio_probe", "audio_extractor", "proxy_generator"]
)
def test_optional_stage_cancelled_error_is_never_downgraded_to_warning(
    tmp_path: Path,
    failing_dependency: str,
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"clip")

    def cancelled(*_args, **_kwargs):
        raise UserFacingError(ErrorCode.CANCELLED, "任务已取消。")

    overrides = {failing_dependency: cancelled}
    job = Job(
        source,
        Operation.VIDEO_AI_PACK,
        tmp_path / "out",
        video_ai_pack_include_audio=failing_dependency != "proxy_generator",
        video_ai_pack_include_proxy=failing_dependency == "proxy_generator",
    )

    with pytest.raises(UserFacingError) as caught:
        _service(**overrides).create_pack(job)

    assert caught.value.code is ErrorCode.CANCELLED
    assert not (tmp_path / "out" / "Video-AI-Pack").exists()


def test_written_manifest_validation_rejects_corrupted_reference(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"clip")
    result = _service().create_pack(Job(source, Operation.VIDEO_AI_PACK, tmp_path / "out"))
    manifest_path = result.output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = tuple(
        VideoFrame(
            item["source_id"],
            frame["frame_id"],
            frame["path"],
            frame["timestamp_seconds"],
        )
        for item in manifest["sources"]
        for frame in item["frames"]
    )
    artifact_paths = [item["path"] for item in manifest["artifacts"]]
    manifest["timeline"] = "../outside.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(UserFacingError) as caught:
        validate_written_video_ai_pack_manifest(
            result.output,
            source_ids=("video-001",),
            frames=frames,
            artifact_paths=artifact_paths,
        )

    assert caught.value.code is ErrorCode.INTEGRITY_FAILED
