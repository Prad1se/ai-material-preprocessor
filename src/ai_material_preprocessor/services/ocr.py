from __future__ import annotations

import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path


class OCRUnavailableError(RuntimeError):
    pass


def _load_rapidocr():
    from rapidocr import RapidOCR

    return RapidOCR()


def _render_pdf(source: Path, work_dir: Path) -> list[tuple[str, Path]]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise OCRUnavailableError("PDF OCR 需要安装 pypdfium2。") from exc
    rendered: list[tuple[str, Path]] = []
    document = pdfium.PdfDocument(str(source))
    try:
        for index in range(len(document)):
            page = document[index]
            output = work_dir / f"page-{index + 1:03d}.png"
            bitmap = page.render(scale=300 / 72)
            bitmap.to_pil().save(output)
            rendered.append((f"第 {index + 1} 页", output))
            bitmap.close()
            page.close()
    finally:
        document.close()
    return rendered


class RapidOCREngine:
    """Local OCR adapter for images, PDF pages and embedded Office images."""

    OFFICE_MEDIA = {
        ".docx": "word/media/",
        ".pptx": "ppt/media/",
        ".xlsx": "xl/media/",
    }
    IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

    def __init__(
        self,
        *,
        engine=None,
        importer: Callable[[], object] = _load_rapidocr,
        pdf_renderer: Callable[[Path, Path], list[tuple[str, Path]]] = _render_pdf,
    ) -> None:
        if engine is None:
            try:
                engine = importer()
            except (ImportError, ModuleNotFoundError) as exc:
                raise OCRUnavailableError(
                    "未安装本地 RapidOCR；请安装 rapidocr、onnxruntime 和 pypdfium2。"
                ) from exc
        self.engine = engine
        self.pdf_renderer = pdf_renderer

    def _recognize(self, path: Path) -> tuple[str, float]:
        result = self.engine(path)
        if hasattr(result, "txts"):
            texts = list(result.txts or ())
            scores = [float(value) for value in (result.scores or ())]
        elif isinstance(result, tuple) and result:
            rows = result[0] or []
            texts = [str(row[1]) for row in rows if len(row) >= 3]
            scores = [float(row[2]) for row in rows if len(row) >= 3]
        else:
            texts, scores = [], []
        text = "\n".join(value.strip() for value in texts if value and value.strip())
        confidence = round(sum(scores) / len(scores), 6) if scores else 0.0
        return text, confidence

    def _office_images(self, source: Path, work_dir: Path) -> list[tuple[str, Path]]:
        prefix = self.OFFICE_MEDIA[source.suffix.lower()]
        extracted: list[tuple[str, Path]] = []
        try:
            with zipfile.ZipFile(source) as archive:
                members = sorted(
                    name
                    for name in archive.namelist()
                    if name.lower().startswith(prefix)
                    and Path(name).suffix.lower() in self.IMAGE_SUFFIXES
                )
                for index, member in enumerate(members, start=1):
                    destination = work_dir / f"embedded-{index:03d}{Path(member).suffix.lower()}"
                    destination.write_bytes(archive.read(member))
                    extracted.append((f"内嵌图片 {index}", destination))
        except zipfile.BadZipFile as exc:
            raise OCRUnavailableError(f"无法读取 Office 文件中的图片：{source.name}") from exc
        return extracted

    def extract(self, source: Path) -> list[tuple[str, str, float]]:
        suffix = source.suffix.lower()
        with tempfile.TemporaryDirectory(prefix="ai-material-ocr-") as temporary:
            work_dir = Path(temporary)
            if suffix in self.IMAGE_SUFFIXES:
                images = [("图片", source)]
            elif suffix == ".pdf":
                images = self.pdf_renderer(source, work_dir)
            elif suffix in self.OFFICE_MEDIA:
                images = self._office_images(source, work_dir)
            else:
                images = []
            results: list[tuple[str, str, float]] = []
            for label, image in images:
                text, confidence = self._recognize(image)
                if text:
                    results.append((label, text, confidence))
            return results
