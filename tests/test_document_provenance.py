from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai_material_preprocessor.services.document_enhancement import (
    EnhancementOptions,
    enhance_document,
)
from ai_material_preprocessor.services.document_provenance import (
    extract_provenance,
    source_label_for_line,
)
from ai_material_preprocessor.services.markdown_quality import check_quality
from ai_material_preprocessor.services.markdown_splitting import split_markdown
from ai_material_preprocessor.services.preview import build_document_preview


def test_ppt_and_ocr_provenance_maps_markdown_lines_to_source_sections() -> None:
    markdown = """<!-- Slide number: 1 -->
# 第一页
内容一

<!-- Slide number: 2 -->
# 第二页
内容二

## OCR 补充文本

### 第 2 页（平均置信度 62.0%）

识别文字
"""

    spans = extract_provenance(markdown, source_suffix=".pptx")

    assert [span.source_type for span in spans] == ["slide", "slide", "ocr"]
    assert [span.label for span in spans] == ["幻灯片 1", "幻灯片 2", "第 2 页"]
    assert spans[2].confidence == 0.62
    assert source_label_for_line(spans, 6) == "幻灯片 2"
    assert source_label_for_line(spans, 13) == "第 2 页"


def test_excel_provenance_preserves_worksheet_relationship() -> None:
    markdown = """# 工作表：成绩
| 姓名 | 分数 |
| --- | --- |
| 小明 | 95 |

# 工作表：统计
| 项目 | 值 |
| --- | --- |
| 平均 | 95 |
"""

    spans = extract_provenance(markdown, source_suffix=".xlsx")

    assert [(span.source_type, span.label) for span in spans] == [
        ("worksheet", "成绩"),
        ("worksheet", "统计"),
    ]
    assert spans[0].start_line == 1 and spans[0].end_line == 5
    assert spans[1].start_line == 6


def test_quality_issues_include_line_and_source_for_empty_page_bad_table_and_heading_jump(
    tmp_path: Path,
) -> None:
    markdown = """<!-- Page: 1 -->
# 第一页

<!-- Page: 2 -->
# 第二页
#### 跳级
| A | B |
| --- | --- |
| only-one |
![缺失](assets/missing.png)
"""

    report = check_quality(
        markdown,
        base_dir=tmp_path,
        max_tokens=1000,
        source_suffix=".pdf",
    )
    issues = {issue.code: issue for issue in report.issues}

    assert {"empty_source_section", "heading_jump", "malformed_table", "missing_image"} <= set(
        issues
    )
    assert issues["heading_jump"].line == 6
    assert issues["heading_jump"].source_label == "第 2 页"
    assert issues["missing_image"].line == 10
    assert issues["missing_image"].source_label == "第 2 页"


def test_splitter_keeps_formula_blocks_whole_and_labels_chunk_sources() -> None:
    markdown = """<!-- Page: 1 -->
# 第一页

第一页内容。第一页内容。第一页内容。

<!-- Page: 2 -->
# 第二页

$$
E = mc^2
x = y + z
$$

第二页内容。第二页内容。第二页内容。
"""

    chunks = split_markdown(markdown, target_tokens=20, max_tokens=40)

    assert len(chunks) >= 2
    assert any("第 1 页" in chunk.source_labels for chunk in chunks)
    assert any("第 2 页" in chunk.source_labels for chunk in chunks)
    formula_chunks = [chunk for chunk in chunks if "E = mc^2" in chunk.content]
    assert len(formula_chunks) == 1
    assert formula_chunks[0].content.count("$$") == 2


def test_splitter_keeps_heading_with_following_content_when_under_hard_limit() -> None:
    markdown = "# 文档\n\n## 章节一\n\n" + ("内容。" * 18) + "\n\n## 章节二\n\n结尾。\n"

    chunks = split_markdown(markdown, target_tokens=20, max_tokens=50)

    for index, chunk in enumerate(chunks[:-1]):
        assert not chunk.content.rstrip().endswith(("## 章节一", "## 章节二")), index


def test_enhancement_reports_heading_jump_found_before_cleaning(tmp_path: Path) -> None:
    source = tmp_path / "讲义.docx"
    source.write_bytes(b"docx")

    result = enhance_document(
        source=source,
        raw_markdown="# 标题\n\n#### 原始跳级\n\n内容\n",
        output_dir=tmp_path / "package",
        options=EnhancementOptions(split_enabled=False),
    )

    issue = next(item for item in result.quality.issues if item.code == "heading_jump")
    assert issue.line == 3
    assert issue.source_label == "Word 文档"


def test_ai_package_manifest_is_compact_traceable_and_has_no_private_source_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "课程.pptx"
    source.write_bytes(b"public-fixture")
    result = enhance_document(
        source=source,
        raw_markdown="<!-- Slide number: 1 -->\n# 第一页\n\n内容\n",
        output_dir=tmp_path / "package",
        options=EnhancementOptions(split_enabled=False),
        tool_versions={"MarkItDown": "0.1.6", "RapidOCR": "1.4.4"},
    )

    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))

    assert manifest["format_version"] == 2
    assert manifest["source"] == {
        "name": "课程.pptx",
        "sha256": hashlib.sha256(b"public-fixture").hexdigest(),
        "format": ".pptx",
    }
    assert manifest["mode"] == "enhanced"
    assert manifest["tools"] == {"MarkItDown": "0.1.6", "RapidOCR": "1.4.4"}
    assert manifest["main_markdown"] == "content.md"
    assert manifest["chunks"] == []
    assert manifest["assets"] == []
    assert manifest["provenance"][0]["label"] == "幻灯片 1"
    assert "source_path" not in manifest
    assert "quality" not in manifest
    assert "target_tokens" not in manifest


def test_document_preview_risk_preserves_issue_location(tmp_path: Path) -> None:
    source = tmp_path / "课件.pptx"
    source.write_bytes(b"pptx")
    preview = build_document_preview(
        source,
        "<!-- Slide number: 2 -->\n# 标题\n\n![缺失](assets/missing.png)\n",
        base_dir=tmp_path,
        options=EnhancementOptions(split_enabled=False),
    )

    risk = next(item for item in preview.risks if item.code == "missing_image")
    assert risk.line == 4
    assert risk.source_label == "幻灯片 2"
