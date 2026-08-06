from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_material_preprocessor.services.ocr import OCRUnavailableError, RapidOCREngine


class FakeRapidOCR:
    def __call__(self, image):
        return SimpleNamespace(txts=("第一行", "第二行"), scores=(0.9, 0.8))


def test_ocr_reads_embedded_office_images(tmp_path: Path) -> None:
    source = tmp_path / "lesson.pptx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("ppt/media/image1.png", b"fake-image")
        archive.writestr("ppt/slides/slide1.xml", b"ignored")

    results = RapidOCREngine(engine=FakeRapidOCR()).extract(source)

    assert results == [("内嵌图片 1", "第一行\n第二行", 0.85)]


def test_ocr_reads_rendered_pdf_pages(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"fake")

    def render(_source: Path, work_dir: Path):
        page = work_dir / "page-001.png"
        page.write_bytes(b"fake-image")
        return [("第 1 页", page)]

    results = RapidOCREngine(engine=FakeRapidOCR(), pdf_renderer=render).extract(source)

    assert results[0][0] == "第 1 页"
    assert results[0][1] == "第一行\n第二行"


def test_missing_ocr_dependency_has_actionable_error() -> None:
    with pytest.raises(OCRUnavailableError, match="RapidOCR"):
        RapidOCREngine(importer=lambda: (_ for _ in ()).throw(ImportError()))
