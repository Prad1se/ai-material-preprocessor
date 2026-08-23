"""Repeatable, privacy-safe local diagnostics reports."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .converters.common import run_command
from .converters.markdown import to_markdown
from .converters.video import keyframes_contact_sheet
from .models import ToolStatus
from .services.config import load_config
from .services.document_enhancement import EnhancementOptions, QualityReport
from .services.environment import detect_tools
from .services.observability import DiagnosticLogger, redact_text, resolve_diagnostics_root


def _safe_check(check: dict[str, Any]) -> dict[str, Any]:
    """Keep only state fields; self-test artifacts are intentionally private."""
    permitted = {"passed", "detail", "error_type", "artifact_created"}
    return {
        key: redact_text(value) if isinstance(value, str) else value
        for key, value in sorted(check.items())
        if key in permitted
    }


def _safe_tools(tools: dict[str, ToolStatus]) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "available": status.available,
            "source": redact_text(status.source),
            "version": redact_text(status.version),
        }
        for name, status in sorted(tools.items())
    }


def write_diagnostic_report(
    output_directory: Path,
    *,
    tools: dict[str, ToolStatus],
    checks: dict[str, dict[str, Any]],
    application_version: str = __version__,
    logger: DiagnosticLogger | None = None,
) -> Path:
    """Write the fixed-format report without user paths, content, or config values."""
    output_directory.mkdir(parents=True, exist_ok=True)
    sanitized_checks = {name: _safe_check(check) for name, check in sorted(checks.items())}
    report: dict[str, Any] = {
        "application": "AI Material Preprocessor",
        "application_version": application_version,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "format": "ai-material-preprocessor-diagnostics-v1",
        "overall": (
            "passed"
            if all(check.get("passed") is not False for check in sanitized_checks.values())
            else "failed"
        ),
        "tools": _safe_tools(tools),
        "checks": sanitized_checks,
    }
    if logger is not None:
        report["recent_events"] = logger.recent_events()
    report_path = output_directory / "diagnostics.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report_path


def default_diagnostic_report_directory() -> Path:
    return resolve_diagnostics_root() / "reports"


def run_self_test(
    output_directory: Path,
    *,
    config: dict | None = None,
    tools: dict[str, ToolStatus] | None = None,
    markdown_converter=None,
    logger: DiagnosticLogger | None = None,
) -> Path:
    """Run synthetic local checks and export a metadata-only report."""
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    active_logger = logger or DiagnosticLogger(output_directory / "events")
    active_logger.record("diagnostics.self_test_started")
    active_config = config or load_config()
    active_tools = tools or detect_tools(active_config, logger=active_logger)
    checks: dict[str, dict[str, Any]] = {}

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
            "artifact_created": markdown_output.is_file(),
        }
    except Exception as exc:
        active_logger.record_failure("diagnostics.markitdown_failed", exc, tool="markitdown")
        checks["markitdown"] = {"passed": False, "error_type": type(exc).__name__}

    ffmpeg = active_tools["ffmpeg"].path
    if ffmpeg:
        try:
            run_command([ffmpeg, "-version"]).stdout.splitlines()[0]
            checks["ffmpeg"] = {"passed": True}
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
                video_source,
                output_directory,
                ffmpeg,
                max_frames=4,
                columns=2,
                logger=active_logger,
            )
            checks["storyboard"] = {
                "passed": sheet.is_file() and (sheet.parent / "manifest.json").is_file(),
                "artifact_created": sheet.is_file(),
            }
        except Exception as exc:
            active_logger.record_failure("diagnostics.ffmpeg_failed", exc, tool="ffmpeg")
            checks["ffmpeg"] = {"passed": False, "error_type": type(exc).__name__}
            checks["storyboard"] = {"passed": False, "error_type": type(exc).__name__}
    else:
        checks["ffmpeg"] = {"passed": None, "detail": "not available"}
        checks["storyboard"] = {"passed": None, "detail": "not available"}

    if active_tools.get("rapidocr", ToolStatus("rapidocr", None)).available:
        try:
            from .services.ocr import RapidOCREngine

            RapidOCREngine(logger=active_logger)
            checks["rapidocr"] = {"passed": True, "detail": "local models loaded"}
        except Exception as exc:
            active_logger.record_failure("diagnostics.rapidocr_failed", exc, tool="rapidocr")
            checks["rapidocr"] = {"passed": False, "error_type": type(exc).__name__}
    else:
        checks["rapidocr"] = {"passed": None, "detail": "not available"}

    active_logger.record(
        "diagnostics.self_test_completed",
        overall="passed"
        if all(value.get("passed") is not False for value in checks.values())
        else "failed",
    )
    return write_diagnostic_report(
        output_directory,
        tools=active_tools,
        checks=checks,
        logger=active_logger,
    )
