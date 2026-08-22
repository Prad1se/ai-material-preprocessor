from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from ai_material_preprocessor.errors import UserFacingError
from ai_material_preprocessor.infrastructure.processes import CancellationToken
from ai_material_preprocessor.models import Job, Operation, ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.services.document_service import DocumentConversionService


def test_document_service_builds_one_context_pack_from_multiple_sources(
    monkeypatch, tmp_path: Path
) -> None:
    sources = (tmp_path / "讲义.txt", tmp_path / "notes.txt")
    original_contents = {}
    enhancement_options = []
    for index, source in enumerate(sources, start=1):
        content = f"# Source {index}\n\nContent {index}.\n"
        source.write_text(content, encoding="utf-8")
        original_contents[source] = source.read_bytes()

    def fake_to_markdown(source, output_root, executable, **kwargs):
        del executable
        enhancement_options.append(kwargs["enhancement_options"])
        package = output_root / f"{source.stem}_AI资料包"
        package.mkdir()
        content = source.read_text(encoding="utf-8")
        (package / "raw.md").write_text(content, encoding="utf-8")
        (package / "content.md").write_text(content, encoding="utf-8")
        (package / "README.md").write_text("Prepared source", encoding="utf-8")
        (package / "manifest.json").write_text(
            json.dumps(
                {
                    "format_version": 2,
                    "source": {"name": source.name, "sha256": "abc"},
                    "provenance": [
                        {
                            "source_type": "document",
                            "label": "源文档",
                            "start_line": 1,
                            "end_line": 3,
                        }
                    ],
                    "warnings": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return package / "content.md"

    monkeypatch.setattr(
        "ai_material_preprocessor.services.document_service.to_markdown", fake_to_markdown
    )
    service = DocumentConversionService(
        {"markitdown": ToolStatus("markitdown", "Python API", version="1")},
        deepcopy(DEFAULT_CONFIG),
    )
    progress = []
    output, reports = service.convert(
        Job(
            sources[0],
            Operation.DOCUMENT_CONTEXT_PACK,
            tmp_path / "out",
            sources=sources,
            context_budget=1000,
            context_ocr_enabled=True,
        ),
        on_progress=lambda value, message: progress.append((value, message)),
    )

    assert (output / "START_HERE.md").is_file()
    assert (output / "sources" / "source-001" / "content.md").is_file()
    assert (output / "sources" / "source-002" / "content.md").is_file()
    assert (output / "sources" / "source-001" / "source-manifest.json").is_file()
    assert not (output / "sources" / "source-001" / "raw.md").exists()
    assert not (output / "sources" / "source-001" / "README.md").exists()
    assert reports[0]["source_count"] == 2
    assert reports[0]["integrity"] == "complete"
    assert all(source.read_bytes() == original_contents[source] for source in sources)
    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.rglob("*")
        if path.is_file() and path.suffix in {".md", ".json"}
    )
    assert str(tmp_path) not in public_text
    assert [message for _value, message in progress] == [
        "Converting source 1 of 2: 讲义.txt",
        "Converting source 2 of 2: notes.txt",
        "Assembling source blocks",
        "Writing Context Pack and integrity report",
        "Context Pack ready",
    ]
    assert all(options.ocr_enabled is True for options in enhancement_options)


def test_context_pack_cancellation_does_not_leave_partial_output(tmp_path: Path) -> None:
    source = tmp_path / "lesson.txt"
    source.write_text("notes", encoding="utf-8")
    token = CancellationToken()
    token.cancel()
    service = DocumentConversionService(
        {"markitdown": ToolStatus("markitdown", "Python API")}, deepcopy(DEFAULT_CONFIG)
    )

    with pytest.raises(UserFacingError, match="任务已取消"):
        service.convert(
            Job(source, Operation.DOCUMENT_CONTEXT_PACK, tmp_path / "out", sources=(source,)),
            cancellation=token,
        )

    assert list((tmp_path / "out").iterdir()) == []
