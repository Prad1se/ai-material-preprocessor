from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .converters.common import run_command
from .converters.markdown import to_markdown
from .converters.video import keyframes_contact_sheet
from .models import ToolStatus
from .services.config import load_config
from .services.document_enhancement import EnhancementOptions, QualityReport
from .services.environment import detect_tools


def run_self_test(
    output_directory: Path,
    *,
    config: dict | None = None,
    tools: dict[str, ToolStatus] | None = None,
    markdown_converter=None,
) -> Path:
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    active_config = config or load_config()
    active_tools = tools or detect_tools(active_config)
    checks: dict[str, dict] = {}

    source = output_directory / "diagnostics-source.html"
    source.write_text(
        "<!doctype html><meta charset='utf-8'><h1>AI 素材预处理工具</h1>"
        "<p>MarkItDown self-test.</p>",
        encoding="utf-8",
    )
    try:
        quality_reports: list[QualityReport] = []
        markdown_output = to_markdown(
            source,
            output_directory,
            active_tools["markitdown"].path,
            converter=markdown_converter,
            enhance=True,
            enhancement_options=EnhancementOptions(
                split_enabled=True, target_tokens=20, max_tokens=40
            ),
            quality_callback=quality_reports.append,
        )
        checks["markitdown"] = {
            "passed": (
                markdown_output.is_file()
                and markdown_output.stat().st_size > 0
                and (markdown_output.parent / "raw.md").is_file()
                and (markdown_output.parent / "manifest.json").is_file()
                and (markdown_output.parent / "README.md").is_file()
                and bool(quality_reports)
                and not (markdown_output.parent / "quality-report.json").exists()
                and not (markdown_output.parent / "quality-report.md").exists()
            ),
            "output": str(markdown_output),
        }
    except Exception as exc:
        checks["markitdown"] = {"passed": False, "error": str(exc)}

    ffmpeg = active_tools["ffmpeg"].path
    if ffmpeg:
        try:
            version = run_command([ffmpeg, "-version"]).stdout.splitlines()[0]
            checks["ffmpeg"] = {"passed": True, "version": version}
            video_source = output_directory / "diagnostics-video.mp4"
            run_command(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=320x240:rate=12",
                    "-t",
                    "0.5",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(video_source),
                ]
            )
            sheet = keyframes_contact_sheet(
                video_source, output_directory, ffmpeg, max_frames=4, columns=2
            )
            checks["storyboard"] = {
                "passed": sheet.is_file() and (sheet.parent / "manifest.json").is_file(),
                "output": str(sheet),
            }
        except Exception as exc:
            checks["ffmpeg"] = {"passed": False, "error": str(exc)}
            checks["storyboard"] = {"passed": False, "error": str(exc)}
    else:
        checks["ffmpeg"] = {"passed": None, "detail": "not available"}
        checks["storyboard"] = {"passed": None, "detail": "not available"}

    if active_tools.get("rapidocr", ToolStatus("rapidocr", None)).available:
        try:
            from .services.ocr import RapidOCREngine

            RapidOCREngine()
            checks["rapidocr"] = {"passed": True, "detail": "local models loaded"}
        except Exception as exc:
            checks["rapidocr"] = {"passed": False, "error": str(exc)}
    else:
        checks["rapidocr"] = {"passed": None, "detail": "not available"}

    report = {
        "application": "AI Material Preprocessor",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "overall": (
            "passed" if all(check["passed"] is not False for check in checks.values()) else "failed"
        ),
        "tools": {
            name: {
                "available": status.available,
                "path": status.path,
                "source": status.source,
            }
            for name, status in active_tools.items()
        },
        "checks": checks,
    }
    report_path = output_directory / "diagnostics.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_path
