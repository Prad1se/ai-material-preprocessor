from __future__ import annotations

import json
import math
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from ..services.files import unique_path
from ..services.metadata import read_media_metadata
from ..services.naming import preview_video_rename
from .common import ConversionError, run_command


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def _progress_prefix(executable: str) -> list[str]:
    return [
        executable, "-hide_banner", "-nostdin", "-progress", "pipe:1",
        "-stats_period", "0.25", "-n",
    ]


def build_compress_command(
    executable: str, source: Path, output: Path, crf: int, preset: str
) -> list[str]:
    return [
        *_progress_prefix(executable), "-i", str(source),
        "-map_metadata", "0", "-c:v", "libx264", "-crf", str(crf),
        "-preset", preset, "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", str(output),
    ]


def build_extract_audio_command(
    executable: str,
    source: Path,
    output: Path,
    audio_format: str,
    bitrate: str,
) -> list[str]:
    command = [*_progress_prefix(executable), "-i", str(source), "-vn"]
    command += ["-c:a", "pcm_s16le"] if audio_format.lower() == "wav" else [
        "-c:a", "libmp3lame", "-b:a", bitrate,
    ]
    return [*command, str(output)]


def build_standardize_command(executable: str, source: Path, output: Path) -> list[str]:
    return [
        *_progress_prefix(executable), "-i", str(source), "-map_metadata", "0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
    ]


def build_keyframe_command(
    executable: str,
    source: Path,
    output_pattern: Path,
    *,
    scene_threshold: float = 0.30,
    max_frames: int = 24,
) -> list[str]:
    threshold = max(0.05, min(0.95, float(scene_threshold)))
    return [
        *_progress_prefix(executable), "-i", str(source),
        "-vf", f"select=gt(scene\\,{threshold:.2f}),scale='min(1920,iw)':-2",
        "-fps_mode", "vfr", "-c:v", "mjpeg", "-pix_fmt", "yuvj420p",
        "-q:v", "2", "-frames:v", str(max(1, max_frames)),
        str(output_pattern),
    ]


def _build_first_frame_command(executable: str, source: Path, output: Path) -> list[str]:
    return [
        *_progress_prefix(executable), "-i", str(source), "-vf", "scale='min(1920,iw)':-2",
        "-frames:v", "1", "-c:v", "mjpeg", "-pix_fmt", "yuvj420p",
        "-q:v", "2", str(output),
    ]


def create_contact_sheet(
    frames: list[Path], output: Path, *, columns: int = 4, cell_width: int = 320
) -> Path:
    if not frames:
        raise ConversionError("没有可用于生成联系表的关键帧。")
    columns = min(max(1, columns), len(frames))
    with Image.open(frames[0]) as first:
        ratio = first.height / max(1, first.width)
    image_height = max(1, round(cell_width * ratio))
    caption_height = 32
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (columns * cell_width, rows * (image_height + caption_height)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, frame in enumerate(frames, start=1):
        row, column = divmod(index - 1, columns)
        with Image.open(frame) as image:
            fitted = ImageOps.contain(image.convert("RGB"), (cell_width, image_height))
            x = column * cell_width + (cell_width - fitted.width) // 2
            y = row * (image_height + caption_height) + (image_height - fitted.height) // 2
            sheet.paste(fitted, (x, y))
        draw.text(
            (column * cell_width + 10, row * (image_height + caption_height) + image_height + 8),
            f"Frame {index:03d}", fill="#222222",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "JPEG", quality=90, optimize=True)
    return output


def parse_progress_line(line: str, duration_seconds: float) -> int | None:
    if line.strip() == "progress=end":
        return 100
    if line.startswith("out_time_us=") and duration_seconds > 0:
        try:
            elapsed = int(line.partition("=")[2]) / 1_000_000
            return max(0, min(99, round(elapsed / duration_seconds * 100)))
        except ValueError:
            return None
    return None


def probe_duration(executable: str, source: Path, *, runner=run_command) -> float:
    result = runner([
        executable, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(source),
    ])
    try:
        return max(0.0, float((result.stdout or "0").strip()))
    except ValueError:
        return 0.0


def _ensure_video(source: Path) -> None:
    if source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ConversionError("请选择受支持的视频文件。")


def _require(path: str | None, tool: str) -> str:
    if not path:
        raise ConversionError(f"未检测到 {tool}，该功能暂不可用。")
    return path


def _run_and_cleanup(command: list[str], output: Path) -> None:
    try:
        run_command(command)
    except Exception:
        if output.exists():
            output.unlink()
        raise


def compress(source: Path, output_root: Path, ffmpeg: str | None, crf: int, preset: str) -> Path:
    _ensure_video(source)
    exe = _require(ffmpeg, "FFmpeg")
    output_root.mkdir(parents=True, exist_ok=True)
    output = unique_path(output_root / f"{source.stem}_compressed.mp4")
    _run_and_cleanup(build_compress_command(exe, source, output, crf, preset), output)
    return output


def extract_audio(
    source: Path, output_root: Path, ffmpeg: str | None, audio_format: str, bitrate: str
) -> Path:
    _ensure_video(source)
    exe = _require(ffmpeg, "FFmpeg")
    extension = ".wav" if audio_format.lower() == "wav" else ".mp3"
    output_root.mkdir(parents=True, exist_ok=True)
    output = unique_path(output_root / f"{source.stem}{extension}")
    _run_and_cleanup(
        build_extract_audio_command(exe, source, output, audio_format, bitrate), output
    )
    return output


def standardize(source: Path, output_root: Path, ffmpeg: str | None) -> Path:
    _ensure_video(source)
    exe = _require(ffmpeg, "FFmpeg")
    output_root.mkdir(parents=True, exist_ok=True)
    output = unique_path(output_root / f"{source.stem}_standard.mp4")
    _run_and_cleanup(build_standardize_command(exe, source, output), output)
    return output


def keyframes_contact_sheet(
    source: Path,
    output_root: Path,
    ffmpeg: str | None,
    *,
    scene_threshold: float = 0.30,
    max_frames: int = 24,
    columns: int = 4,
) -> Path:
    _ensure_video(source)
    exe = _require(ffmpeg, "FFmpeg")
    output_root.mkdir(parents=True, exist_ok=True)
    base = output_root / f"{source.stem}_关键帧包"
    package = base
    counter = 2
    while package.exists():
        package = output_root / f"{base.name}_{counter}"
        counter += 1
    frames_dir = package / "frames"
    frames_dir.mkdir(parents=True)
    pattern = frames_dir / "frame_%03d.jpg"
    try:
        try:
            run_command(build_keyframe_command(
                exe, source, pattern, scene_threshold=scene_threshold, max_frames=max_frames
            ))
        except ConversionError:
            pass
        frames = sorted(frames_dir.glob("frame_*.jpg"))
        if not frames:
            fallback = frames_dir / "frame_001.jpg"
            run_command(_build_first_frame_command(exe, source, fallback))
            frames = [fallback]
        contact_sheet = create_contact_sheet(frames, package / "contact-sheet.jpg", columns=columns)
        manifest = {
            "package_type": "video_keyframes",
            "source": source.name,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "scene_threshold": scene_threshold,
            "max_frames": max_frames,
            "frame_count": len(frames),
            "contact_sheet": contact_sheet.name,
            "frames": [f"frames/{path.name}" for path in frames],
        }
        (package / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return contact_sheet
    except Exception:
        if package.exists():
            shutil.rmtree(package, ignore_errors=True)
        raise


def rename_copy(
    source: Path,
    output_root: Path,
    ffprobe: str | None,
    location_override: str,
    index: int = 1,
    *,
    exiftool: str | None = None,
    ffmpeg: str | None = None,
    template: str = "{date}_{time}_{location}_{index}",
) -> Path:
    _ensure_video(source)
    metadata = read_media_metadata(
        source, exiftool, ffprobe, ffmpeg=ffmpeg
    )
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root
    preview = preview_video_rename(
        source, destination, metadata, template, index, location_override
    )
    output = preview.output
    shutil.copy2(source, output)
    return output
