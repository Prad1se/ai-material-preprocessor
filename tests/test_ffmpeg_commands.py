from pathlib import Path

import pytest

from ai_material_preprocessor.converters import video
from ai_material_preprocessor.converters.common import ConversionError
from ai_material_preprocessor.converters.video import (
    build_compress_command,
    build_extract_audio_command,
    build_keyframe_command,
    build_standardize_command,
    parse_keyframe_timestamps,
    parse_progress_line,
    probe_duration,
)
from ai_material_preprocessor.errors import ErrorCode
from ai_material_preprocessor.infrastructure.processes import CancellationToken


def test_compress_command_never_overwrites_and_reports_progress() -> None:
    command = build_compress_command(
        "ffmpeg.exe", Path("input.mp4"), Path("output.mp4"), crf=23, preset="medium"
    )
    assert "-n" in command
    assert "-y" not in command
    assert command[command.index("-progress") + 1] == "pipe:1"
    assert command[-1] == "output.mp4"


def test_audio_command_supports_lossless_wav() -> None:
    command = build_extract_audio_command(
        "ffmpeg.exe", Path("input.mp4"), Path("audio.wav"), "wav", "192k"
    )
    assert command[command.index("-c:a") : command.index("-c:a") + 2] == ["-c:a", "pcm_s16le"]


def test_standardize_command_preserves_metadata_and_uses_compatible_pixel_format() -> None:
    command = build_standardize_command("ffmpeg.exe", Path("input.mov"), Path("output.mp4"))
    assert command[command.index("-map_metadata") : command.index("-map_metadata") + 2] == [
        "-map_metadata",
        "0",
    ]
    assert command[command.index("-pix_fmt") : command.index("-pix_fmt") + 2] == [
        "-pix_fmt",
        "yuv420p",
    ]


def test_progress_parser_accepts_out_time_microseconds() -> None:
    assert parse_progress_line("out_time_us=2500000", duration_seconds=10) == 25
    assert parse_progress_line("progress=end", duration_seconds=10) == 100
    assert parse_progress_line("frame=20", duration_seconds=10) is None


def test_probe_duration_uses_machine_readable_ffprobe_output() -> None:
    commands: list[list[str]] = []

    class Result:
        stdout = "12.5\n"

    def runner(command: list[str], **_kwargs):
        commands.append(command)
        return Result()

    assert probe_duration("ffprobe.exe", Path("clip.mp4"), runner=runner) == 12.5
    assert "format=duration" in commands[0]


def test_keyframe_command_uses_scene_detection_and_caps_output() -> None:
    command = build_keyframe_command(
        "ffmpeg.exe",
        Path("input.mp4"),
        Path("frames/frame_%03d.jpg"),
        scene_threshold=0.32,
        max_frames=18,
    )
    filter_value = command[command.index("-vf") + 1]
    assert "gt(scene\\,0.32)" in filter_value
    assert "showinfo" in filter_value
    assert command[command.index("-frames:v") + 1] == "18"
    assert "-n" in command


def test_keyframe_timestamp_parser_reads_showinfo_pts_times() -> None:
    stderr = """
[Parsed_showinfo_1 @ 000] n:0 pts:1280 pts_time:1.25 pos:0
[Parsed_showinfo_1 @ 000] n:1 pts:67072 pts_time:65.5 pos:1
"""

    assert parse_keyframe_timestamps(stderr) == (1.25, 65.5)


def test_video_conversion_forwards_cancellation_and_removes_partial_output(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    token = CancellationToken()

    def cancelled_run(command: list[str], *, cancellation=None, tool_name=""):
        assert cancellation is token
        Path(command[-1]).write_bytes(b"partial")
        raise ConversionError(
            "任务已取消。",
            code=ErrorCode.CANCELLED,
            retryable=True,
        )

    monkeypatch.setattr(video, "run_command", cancelled_run)

    with pytest.raises(ConversionError):
        video.standardize(
            source,
            tmp_path / "out",
            "ffmpeg.exe",
            cancellation=token,
        )

    assert not list((tmp_path / "out").glob("*.mp4"))


def test_video_conversion_reports_machine_readable_ffmpeg_progress(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    values: list[int] = []

    def fake_run(command: list[str], *, stdout_line_callback=None, **_kwargs):
        assert stdout_line_callback is not None
        stdout_line_callback("out_time_us=2500000")
        stdout_line_callback("progress=end")
        Path(command[-1]).write_bytes(b"video")

    monkeypatch.setattr(video, "run_command", fake_run)

    video.standardize(
        source,
        tmp_path / "out",
        "ffmpeg.exe",
        duration_seconds=10,
        progress_callback=lambda percent, _message: values.append(percent),
    )

    assert values == [25, 100]


def test_video_cancellation_after_ffmpeg_exit_removes_derived_output(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    token = CancellationToken()

    def fake_run(command: list[str], **_kwargs):
        Path(command[-1]).write_bytes(b"video")
        token.cancel()

    monkeypatch.setattr(video, "run_command", fake_run)

    with pytest.raises(ConversionError) as raised:
        video.standardize(
            source,
            tmp_path / "out",
            "ffmpeg.exe",
            cancellation=token,
        )

    assert raised.value.code is ErrorCode.CANCELLED
    assert not list((tmp_path / "out").glob("*.mp4"))
