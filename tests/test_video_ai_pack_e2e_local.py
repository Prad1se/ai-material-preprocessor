from __future__ import annotations

import hashlib
import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from ai_material_preprocessor.infrastructure.processes import CancellationToken
from ai_material_preprocessor.models import Job, Operation, ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.services.video_ai_pack import VideoAIPackService


def _tool(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or not Path(value).is_file():
        pytest.skip(f"{name} does not point to a local executable")
    return value


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _synthetic_sources(tmp_path: Path, ffmpeg: str) -> tuple[Path, Path, Path]:
    audio = tmp_path / "带音频.mp4"
    silent = tmp_path / "无音频.mp4"
    alternate = tmp_path / "不同编码.mp4"
    _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=640x360:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=2",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(audio),
        ]
    )
    _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=480x270:rate=12:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(silent),
        ]
    )
    _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=10:duration=2",
            "-c:v",
            "mpeg4",
            str(alternate),
        ]
    )
    return audio, silent, alternate


def test_real_video_ai_pack_pipeline_with_synthetic_sources(tmp_path: Path) -> None:
    ffmpeg = _tool("AI_MATERIAL_E2E_FFMPEG")
    ffprobe = _tool("AI_MATERIAL_E2E_FFPROBE")
    sources = _synthetic_sources(tmp_path, ffmpeg)
    hashes = {source: _sha256(source) for source in sources}
    service = VideoAIPackService(
        {
            "ffmpeg": ToolStatus("ffmpeg", ffmpeg),
            "ffprobe": ToolStatus("ffprobe", ffprobe),
            "exiftool": ToolStatus("exiftool", None),
        },
        deepcopy(DEFAULT_CONFIG),
    )

    single = service.create_pack(
        Job(
            sources[0],
            Operation.VIDEO_AI_PACK,
            tmp_path / "single",
            video_ai_pack_include_audio=True,
            video_ai_pack_include_proxy=False,
        )
    )
    multiple = service.create_pack(
        Job(
            sources[0],
            Operation.VIDEO_AI_PACK,
            tmp_path / "multiple",
            sources=sources,
            video_ai_pack_include_audio=True,
            video_ai_pack_include_proxy=False,
        )
    )
    proxied = service.create_pack(
        Job(
            sources[2],
            Operation.VIDEO_AI_PACK,
            tmp_path / "proxied",
            video_ai_pack_include_audio=False,
            video_ai_pack_include_proxy=True,
        )
    )

    assert (single.output / "sources" / "video-001" / "audio" / "audio.wav").is_file()
    assert not (single.output / "sources" / "video-001" / "proxy").exists()
    assert (proxied.output / "sources" / "video-001" / "proxy" / "proxy.mp4").is_file()
    assert multiple.report["source_count"] == 3
    assert multiple.report["integrity"]["ok"] is True
    manifest = json.loads((multiple.output / "manifest.json").read_text(encoding="utf-8"))
    timeline = json.loads((multiple.output / "timeline.json").read_text(encoding="utf-8"))
    assert [item["source_id"] for item in manifest["sources"]] == [
        "video-001",
        "video-002",
        "video-003",
    ]
    assert all(item["timestamp_seconds"] is not None for item in timeline["entries"])
    assert manifest["sources"][1]["audio"]["status"] == "unavailable"
    assert any(
        warning["source_id"] == "video-002" and warning["code"] == "audio_unavailable"
        for warning in manifest["warnings"]
    )
    assert all((multiple.output / item["contact_sheet"]).is_file() for item in manifest["sources"])
    assert all(item["frames"] for item in manifest["sources"])
    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in multiple.output.rglob("*")
        if path.is_file() and path.suffix in {".json", ".md"}
    )
    assert str(tmp_path) not in public_text
    assert all(_sha256(source) == hashes[source] for source in sources)

    cancellation = CancellationToken()
    cancellation.cancel()
    cancelled_root = tmp_path / "cancelled"
    with pytest.raises(Exception, match="任务已取消"):
        service.create_pack(
            Job(
                sources[0],
                Operation.VIDEO_AI_PACK,
                cancelled_root,
                video_ai_pack_include_audio=False,
            ),
            cancellation=cancellation,
        )
    assert not cancelled_root.exists() or list(cancelled_root.iterdir()) == []
