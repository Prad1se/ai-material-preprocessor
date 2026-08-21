from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...application.preview_registry import PreviewRequest
from ...models import Operation


@dataclass(frozen=True)
class DocumentPreviewPlan:
    title: str
    sources: tuple[Path, ...]
    parameters: dict[str, str]
    note: str


class DocumentPreviewProvider:
    def build(self, request: PreviewRequest) -> DocumentPreviewPlan:
        if request.operation is Operation.TO_MARKDOWN:
            note = "转换后将显示清洗后的 Markdown、标题结构、拆分长度、OCR 页面和风险提示。"
        elif request.operation is Operation.DOCUMENT_CONTEXT_PACK:
            note = (
                "完整估算会在预处理后写入 Context Report。系统按确定性顺序安全分包，"
                "不会为了满足预算而有意删除内容。"
            )
        elif request.operation is Operation.TO_PDF:
            note = "普通 PDF 转换只生成目标文件；处理记录保存在应用数据目录。"
        else:
            raise ValueError(f"{request.operation.name} is not a document preview operation.")
        return DocumentPreviewPlan(
            "AI Context Pack 预览"
            if request.operation is Operation.DOCUMENT_CONTEXT_PACK
            else "文档处理参数预览",
            request.sources,
            {key: str(value) for key, value in request.parameters.items()},
            note,
        )
