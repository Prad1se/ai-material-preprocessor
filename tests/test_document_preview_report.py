from __future__ import annotations

from pathlib import Path

from ai_material_preprocessor.models import Job, Operation, ToolStatus
from ai_material_preprocessor.services import document_service
from ai_material_preprocessor.services.document_service import DocumentConversionService


def test_document_service_returns_application_preview_with_quality_report(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "课程 资料.pptx"
    source.write_bytes(b"pptx")
    output = tmp_path / "result" / "课程 资料_AI资料包" / "content.md"
    output.parent.mkdir(parents=True)
    output.write_text(
        "# 标题\n\n## 章节\n\n| 项目 | 值 |\n| --- | --- |\n| A | 1 |\n",
        encoding="utf-8",
    )

    def fake_convert(*_args, **_kwargs) -> Path:
        return output

    monkeypatch.setattr(document_service, "to_markdown", fake_convert)
    service = DocumentConversionService(
        {"markitdown": ToolStatus("markitdown", "Python API")},
        {
            "document": {
                "mode": "enhanced",
                "split_enabled": True,
                "target_tokens": 40,
                "max_tokens": 60,
                "ocr_enabled": False,
            }
        },
    )

    result, reports = service.convert(Job(source, Operation.TO_MARKDOWN, tmp_path / "result"))

    assert result == output
    assert len(reports) == 1
    assert reports[0]["source"] == source.name
    assert reports[0]["cleaned_preview"].startswith("# 标题")
    assert reports[0]["headings"][1]["title"] == "章节"
    assert reports[0]["chunks"]
    assert reports[0]["parameters"]["模式"] == "AI 增强"
