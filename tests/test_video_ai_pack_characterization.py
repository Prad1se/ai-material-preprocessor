from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from ai_material_preprocessor.converters import video
from ai_material_preprocessor.converters.common import ConversionError
from ai_material_preprocessor.errors import ErrorCode
from ai_material_preprocessor.infrastructure.processes import CancellationToken
from ai_material_preprocessor.services.metadata import read_media_metadata


def _write_frame(path: Path, color: str = "white") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (160, 90), color).save(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_keyframes_contact_sheet_preserves_existing_package_and_showinfo_contract(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "课程录像.mp4"
    source.write_bytes(b"original-video")
    source_hash = _sha256(source)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs):
        calls.append(command)
        pattern = Path(command[-1])
        _write_frame(pattern.parent / "frame_001.jpg", "red")
        _write_frame(pattern.parent / "frame_002.jpg", "blue")
        return SimpleNamespace(
            stderr=(
                "[Parsed_showinfo_1 @ 000] n:0 pts_time:1.25\n"
                "[Parsed_showinfo_1 @ 000] n:1 pts_time:65.5\n"
            )
        )

    monkeypatch.setattr(video, "run_command", fake_run)

    contact_sheet = video.keyframes_contact_sheet(
        source,
        tmp_path / "outputs",
        "ffmpeg.exe",
        columns=2,
    )

    package = tmp_path / "outputs" / "课程录像_关键帧包"
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert contact_sheet == package / "contact-sheet.jpg"
    assert manifest["package_type"] == "video_keyframes"
    assert manifest["source"] == "课程录像.mp4"
    assert manifest["frame_count"] == 2
    assert manifest["contact_sheet"] == "contact-sheet.jpg"
    assert [item["file"] for item in manifest["frames"]] == [
        "frames/frame_001.jpg",
        "frames/frame_002.jpg",
    ]
    assert [item["timestamp_seconds"] for item in manifest["frames"]] == [1.25, 65.5]
    assert "showinfo" in calls[0][calls[0].index("-vf") + 1]
    assert _sha256(source) == source_hash


def test_keyframes_contact_sheet_uses_first_frame_fallback_at_zero_seconds(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    calls = 0

    def fake_run(command: list[str], **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConversionError("场景检测失败。", code=ErrorCode.EXTERNAL_TOOL_FAILED)
        _write_frame(Path(command[-1]), "green")
        return SimpleNamespace(stderr="")

    monkeypatch.setattr(video, "run_command", fake_run)

    contact_sheet = video.keyframes_contact_sheet(source, tmp_path / "outputs", "ffmpeg.exe")

    manifest = json.loads((contact_sheet.parent / "manifest.json").read_text(encoding="utf-8"))
    assert calls == 2
    assert manifest["frame_count"] == 1
    assert manifest["frames"] == [{"file": "frames/frame_001.jpg", "timestamp_seconds": 0.0}]


def test_keyframes_contact_sheet_cancellation_removes_partial_package(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    token = CancellationToken()

    def cancelled_run(command: list[str], *, cancellation=None, **_kwargs):
        assert cancellation is token
        _write_frame(Path(command[-1]), "yellow")
        raise ConversionError("任务已取消。", code=ErrorCode.CANCELLED, retryable=True)

    monkeypatch.setattr(video, "run_command", cancelled_run)

    with pytest.raises(ConversionError) as raised:
        video.keyframes_contact_sheet(
            source,
            tmp_path / "outputs",
            "ffmpeg.exe",
            cancellation=token,
        )

    assert raised.value.code is ErrorCode.CANCELLED
    assert not (tmp_path / "outputs" / "clip_关键帧包").exists()


def test_keyframes_contact_sheet_avoids_existing_package_directory(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    output_root = tmp_path / "outputs"
    existing = output_root / "clip_关键帧包"
    existing.mkdir(parents=True)
    (existing / "keep.txt").write_text("user result", encoding="utf-8")

    def fake_run(command: list[str], **_kwargs):
        pattern = Path(command[-1])
        _write_frame(pattern.parent / "frame_001.jpg")
        return SimpleNamespace(stderr="[showinfo] pts_time:0.5")

    monkeypatch.setattr(video, "run_command", fake_run)

    result = video.keyframes_contact_sheet(source, output_root, "ffmpeg.exe")

    assert result.parent.name == "clip_关键帧包_2"
    assert (existing / "keep.txt").read_text(encoding="utf-8") == "user result"


def test_extract_audio_wav_writes_pcm_output_and_avoids_collision(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "课程录像.mp4"
    source.write_bytes(b"video")
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    (output_root / "课程录像.wav").write_bytes(b"existing")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"wav-data")
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(video, "run_command", fake_run)

    result = video.extract_audio(source, output_root, "ffmpeg.exe", "wav", "192k")

    assert result == output_root / "课程录像_2.wav"
    assert result.read_bytes() == b"wav-data"
    assert commands[0][commands[0].index("-c:a") : commands[0].index("-c:a") + 2] == [
        "-c:a",
        "pcm_s16le",
    ]
    assert "-vn" in commands[0]
    assert (output_root / "课程录像.wav").read_bytes() == b"existing"


def test_extract_audio_cancellation_removes_partial_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    token = CancellationToken()

    def cancelled_run(command: list[str], *, cancellation=None, **_kwargs):
        assert cancellation is token
        Path(command[-1]).write_bytes(b"partial-wav")
        raise ConversionError("任务已取消。", code=ErrorCode.CANCELLED, retryable=True)

    monkeypatch.setattr(video, "run_command", cancelled_run)

    with pytest.raises(ConversionError) as raised:
        video.extract_audio(
            source,
            tmp_path / "outputs",
            "ffmpeg.exe",
            "wav",
            "192k",
            cancellation=token,
        )

    assert raised.value.code is ErrorCode.CANCELLED
    assert not list((tmp_path / "outputs").glob("*.wav"))


def test_metadata_reader_fallback_order_reaches_file_time_after_tool_failures(
    tmp_path: Path,
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    calls: list[str] = []

    def failing_runner(command: list[str], **_kwargs):
        calls.append(command[0])
        raise RuntimeError("metadata tool failed")

    result = read_media_metadata(
        source,
        "exiftool.exe",
        "ffprobe.exe",
        ffmpeg="ffmpeg.exe",
        runner=failing_runner,
    )

    assert calls == ["exiftool.exe", "ffprobe.exe", "ffmpeg.exe"]
    assert result.source == "文件时间"
    assert result.capture_time_source == "文件修改时间"
