from __future__ import annotations

import json
from pathlib import Path

from ai_material_preprocessor.services.document_enhancement import (
    EnhancementOptions,
    check_quality,
    clean_markdown,
    enhance_document,
    split_markdown,
)


def test_cleaning_repairs_structure_without_touching_fenced_code() -> None:
    source = """# 标题



#### 跳级标题

```python
print('a')


print('b')
```

公式：\\(x + y\\)


"""
    cleaned = clean_markdown(source, source_suffix=".docx")
    assert "\n\n\n" not in cleaned.replace("print('a')\n\n\nprint('b')", "")
    assert "## 跳级标题" in cleaned
    assert "print('a')\n\n\nprint('b')" in cleaned
    assert "公式：$x + y$" in cleaned
    assert cleaned.endswith("\n")


def test_ppt_cleaning_adds_slide_separators_and_removes_repeated_template() -> None:
    source = """<!-- Slide number: 1 -->
# 第一页
课程名称
内容一

<!-- Slide number: 2 -->
# 第二页
课程名称
内容二

<!-- Slide number: 3 -->
# 第三页
课程名称
内容三
"""
    cleaned = clean_markdown(source, source_suffix=".pptx")
    assert cleaned.count("课程名称") == 0
    assert cleaned.count("<!-- Slide number:") == 3
    assert cleaned.count("\n---\n") == 2
    assert "内容一" in cleaned and "内容三" in cleaned


def test_page_markers_allow_repeated_headers_and_footers_to_be_removed() -> None:
    source = """<!-- Page: 1 -->
课程资料
第一页内容
第 1 页
<!-- Page: 2 -->
课程资料
第二页内容
第 2 页
<!-- Page: 3 -->
课程资料
第三页内容
第 3 页
"""
    cleaned = clean_markdown(source, source_suffix=".pdf")
    assert "课程资料" not in cleaned
    assert "第一页内容" in cleaned and "第三页内容" in cleaned


def test_excel_cleaning_labels_each_worksheet() -> None:
    source = """## 成绩
| 姓名 | 分数 |
| --- | --- |
| 小明 | 95 |

## 统计
| 项目 | 值 |
| --- | --- |
| 平均 | 95 |
"""
    cleaned = clean_markdown(source, source_suffix=".xlsx")
    assert "# 工作表：成绩" in cleaned
    assert "# 工作表：统计" in cleaned


def test_image_paths_are_copied_and_rewritten_relative_to_content(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "figure.png").write_bytes(b"image")
    output_dir = tmp_path / "result"
    result = enhance_document(
        source=source_dir / "lesson.docx",
        raw_markdown="![图](figure.png)",
        output_dir=output_dir,
        options=EnhancementOptions(split_enabled=False),
    )
    content = result.content.read_text(encoding="utf-8")
    assert "![图](assets/figure.png)" in content
    assert (output_dir / "assets" / "figure.png").read_bytes() == b"image"


def test_quality_check_finds_broken_images_unclosed_fence_and_oversize(tmp_path: Path) -> None:
    text = "# 标题\n\n![缺失](assets/missing.png)\n\n```python\n" + ("内容" * 100)
    report = check_quality(text, base_dir=tmp_path, max_tokens=20)
    codes = {issue.code for issue in report.issues}
    assert {"missing_image", "unclosed_code_fence", "oversized_document"} <= codes
    assert report.score < 100


def test_split_markdown_respects_hard_limit_and_keeps_headings() -> None:
    text = "# 总标题\n\n" + "\n\n".join(
        f"## 第 {index} 节\n\n" + (f"第{index}节内容。" * 20) for index in range(1, 7)
    )
    chunks = split_markdown(text, target_tokens=80, max_tokens=120)
    assert len(chunks) > 1
    assert all(chunk.estimated_tokens <= 120 for chunk in chunks)
    assert all("# 总标题" in chunk.content for chunk in chunks)
    assert "第 1 节" in chunks[0].content


def test_enhancement_keeps_quality_in_memory_and_writes_content_chunks_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "lesson.pptx"
    source.write_bytes(b"fake")
    output = tmp_path / "enhanced"
    markdown = "<!-- Slide number: 1 -->\n# 标题\n\n" + ("内容。" * 80)
    result = enhance_document(
        source=source,
        raw_markdown=markdown,
        output_dir=output,
        options=EnhancementOptions(split_enabled=True, target_tokens=40, max_tokens=60),
    )
    assert result.raw.read_text(encoding="utf-8") == markdown
    assert result.content.is_file()
    assert result.quality.score >= 0
    assert not (output / "quality-report.json").exists()
    assert not (output / "quality-report.md").exists()
    assert result.manifest and result.manifest.is_file()
    assert result.readme.is_file()
    assert result.chunks
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["source"] == "lesson.pptx"
    assert manifest["package_type"] == "ai_document_package"
    assert manifest["quality"]["score"] >= 0
    assert manifest["files"]["content"] == "content.md"
    assert "quality_markdown" not in manifest["files"]
    assert "quality_json" not in manifest["files"]
    assert manifest["chunk_count"] == len(result.chunks)
    assert "从这里开始" in result.readme.read_text(encoding="utf-8")


def test_short_document_does_not_create_redundant_chunks_folder(tmp_path: Path) -> None:
    source = tmp_path / "short.docx"
    source.write_bytes(b"fake")
    output = tmp_path / "package"

    result = enhance_document(
        source=source,
        raw_markdown="# 简短文档\n\n只有一小段内容。\n",
        output_dir=output,
        options=EnhancementOptions(split_enabled=True, target_tokens=4000, max_tokens=6000),
    )

    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert result.chunks == ()
    assert not (output / "chunks").exists()
    assert manifest["chunk_count"] == 0
    assert "读取 `content.md`" in result.readme.read_text(encoding="utf-8")


def test_optional_ocr_text_is_appended_through_injected_engine(tmp_path: Path) -> None:
    class FakeOCR:
        def extract(self, source: Path):
            return [("图片 1", "识别出的文字", 0.96)]

    source = tmp_path / "scan.pdf"
    source.write_bytes(b"fake")
    result = enhance_document(
        source=source,
        raw_markdown="# 扫描件\n",
        output_dir=tmp_path / "result",
        options=EnhancementOptions(ocr_enabled=True, split_enabled=False),
        ocr_engine=FakeOCR(),
    )
    content = result.content.read_text(encoding="utf-8")
    assert "## OCR 补充文本" in content
    assert "识别出的文字" in content
    assert "96.0%" in content


def test_ocr_repeated_page_headers_are_removed(tmp_path: Path) -> None:
    class FakeOCR:
        def extract(self, source: Path):
            return [
                ("第 1 页", "课程资料\n第一页内容", 0.9),
                ("第 2 页", "课程资料\n第二页内容", 0.9),
                ("第 3 页", "课程资料\n第三页内容", 0.9),
            ]

    source = tmp_path / "scan.pdf"
    source.write_bytes(b"fake")
    result = enhance_document(
        source=source,
        raw_markdown="",
        output_dir=tmp_path / "result",
        options=EnhancementOptions(ocr_enabled=True, split_enabled=False),
        ocr_engine=FakeOCR(),
    )
    content = result.content.read_text(encoding="utf-8")
    assert "课程资料" not in content
    assert "第一页内容" in content and "第三页内容" in content
