import json
from pathlib import Path

import pytest

from ai_material_preprocessor.models import ToolStatus
from ai_material_preprocessor.services.observability import DiagnosticLogger, redact_text


def test_logger_redacts_paths_secrets_and_document_content(tmp_path: Path) -> None:
    logger = DiagnosticLogger(tmp_path, clock=lambda: "2026-08-23T10:00:00+08:00")

    logger.record_failure(
        "metadata.ffprobe_failed",
        RuntimeError(r"D:\Users\Pradise\Documents\private.docx token=secret-value"),
        tool="ffprobe",
        source_suffix=".mp4",
    )

    event = json.loads((tmp_path / "events-2026-08-23.jsonl").read_text(encoding="utf-8"))
    assert event == {
        "event": "metadata.ffprobe_failed",
        "level": "error",
        "schema_version": 1,
        "source_suffix": ".mp4",
        "timestamp": "2026-08-23T10:00:00+08:00",
        "tool": "ffprobe",
        "error_type": "RuntimeError",
    }


def test_redact_text_removes_windows_and_posix_absolute_paths() -> None:
    assert redact_text(r"bad D:\Users\Pradise\secret.docx /home/pradise/private.pdf") == (
        "bad <redacted-path> <redacted-path>"
    )


def test_diagnostic_report_serializes_tool_state_without_executable_paths(tmp_path: Path) -> None:
    from ai_material_preprocessor.diagnostics import write_diagnostic_report

    report_path = write_diagnostic_report(
        tmp_path,
        tools={"ffprobe": ToolStatus("ffprobe", r"D:\Tools\ffprobe.exe", "配置", "6.1")},
        checks={"ffprobe": {"passed": True, "output": r"C:\Users\Pradise\private.mp4"}},
        application_version="2.0.0",
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    rendered = report_path.read_text(encoding="utf-8")
    assert report["tools"]["ffprobe"] == {
        "available": True,
        "source": "配置",
        "version": "6.1",
    }
    assert report["checks"]["ffprobe"] == {"passed": True}
    assert "Pradise" not in rendered
    assert "ffprobe.exe" not in rendered


def test_metadata_fallback_records_tool_failure_without_source_path(tmp_path: Path) -> None:
    from ai_material_preprocessor.services.metadata import read_media_metadata

    source = tmp_path / "private-video.mp4"
    source.write_bytes(b"video")
    logger = DiagnosticLogger(tmp_path / "logs", clock=lambda: "2026-08-23T10:00:00+08:00")

    read_media_metadata(
        source,
        "exiftool.exe",
        None,
        logger=logger,
        runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("private")),
    )

    event = json.loads((tmp_path / "logs" / "events-2026-08-23.jsonl").read_text(encoding="utf-8"))
    assert event["event"] == "metadata.exiftool_failed"
    assert "private-video" not in json.dumps(event)


def test_ocr_initialization_failure_records_only_failure_type(tmp_path: Path) -> None:
    from ai_material_preprocessor.services.ocr import OCRUnavailableError, RapidOCREngine

    logger = DiagnosticLogger(tmp_path, clock=lambda: "2026-08-23T10:00:00+08:00")
    try:
        RapidOCREngine(
            importer=lambda: (_ for _ in ()).throw(ImportError(r"C:\Users\Pradise\private")),
            logger=logger,
        )
    except OCRUnavailableError:
        pass
    else:
        raise AssertionError("RapidOCR initialization should fail")

    event = json.loads((tmp_path / "events-2026-08-23.jsonl").read_text(encoding="utf-8"))
    assert event["event"] == "ocr.initialization_failed"
    assert event["error_type"] == "ImportError"


def test_keyframe_failure_is_logged_without_source_name(monkeypatch, tmp_path: Path) -> None:
    from ai_material_preprocessor.converters import video
    from ai_material_preprocessor.converters.common import ConversionError

    source = tmp_path / "private-video.mp4"
    source.write_bytes(b"video")
    logger = DiagnosticLogger(tmp_path / "logs", clock=lambda: "2026-08-23T10:00:00+08:00")
    monkeypatch.setattr(
        video,
        "run_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConversionError("C:/private.mp4")),
    )

    with pytest.raises(ConversionError):
        video.keyframes_contact_sheet(source, tmp_path / "out", "ffmpeg.exe", logger=logger)

    rendered = (tmp_path / "logs" / "events-2026-08-23.jsonl").read_text(encoding="utf-8")
    assert "keyframes.contact_sheet_failed" in rendered
    assert "private-video" not in rendered
