from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..preview_models import VideoPreview
from ..services.source_map import SourceMap
from .source_map_view import SourceMapView


def format_bytes(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _close_buttons(dialog: QDialog) -> QDialogButtonBox:
    buttons = QDialogButtonBox()
    close_button = QPushButton("关闭")
    close_button.clicked.connect(dialog.reject)
    buttons.addButton(close_button, QDialogButtonBox.ButtonRole.RejectRole)
    return buttons


class DocumentReportDialog(QDialog):
    """Application-only document quality report; it never writes report files."""

    def __init__(
        self,
        reports: list[dict],
        outputs: list[str],
        parent: QWidget | None = None,
        source_map: SourceMap | None = None,
    ) -> None:
        super().__init__(parent)
        is_context_pack = any(report.get("context_pack_version") == 1 for report in reports)
        self.setWindowTitle(
            "AI Context Pack 与 Source Map" if is_context_pack else "转换质量与 AI 阅读预览"
        )
        self.resize(980, 720)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("报告仅显示在应用中；不会在输出目录额外生成 Markdown 或 JSON 报告。"))
        tabs = QTabWidget()
        self.markdown_preview = QPlainTextEdit()
        self.outline = QTreeWidget()
        self.chunk_table = QTableWidget()
        self.ocr_table = QTableWidget()
        self.risk_list = QListWidget()
        self.context_pack_summary = QLabel()
        self.warning_list = QListWidget()
        self.source_map_view = SourceMapView()
        for index, report in enumerate(reports):
            page, widgets = self._report_page(report, outputs)
            tab_title = (
                "AI Context Pack"
                if report.get("context_pack_version") == 1
                else str(report.get("source") or f"文档 {index + 1}")
            )
            tabs.addTab(page, tab_title)
            if index == 0 and widgets is not None:
                (
                    self.markdown_preview,
                    self.outline,
                    self.chunk_table,
                    self.ocr_table,
                    self.risk_list,
                ) = widgets
        if source_map is not None:
            self.source_map_view.back_button.setVisible(False)
            self.source_map_view.set_source_map(source_map)
            tabs.addTab(self.source_map_view, "Source Map")
            tabs.setCurrentWidget(self.source_map_view)
        root.addWidget(tabs)
        root.addWidget(_close_buttons(self))

    def _report_page(self, report: dict, outputs: list[str]):
        if report.get("context_pack_version") == 1:
            return self._context_pack_page(report, outputs), None
        page = QWidget()
        layout = QVBoxLayout(page)
        summary = QLabel(
            f"质量分 {report.get('score', 0)}/100 · "
            f"约 {report.get('estimated_tokens', 0)} tokens · "
            f"{len(report.get('chunks') or [])} 个拆分"
        )
        summary.setObjectName("previewSummary")
        layout.addWidget(summary)
        parameters = QFormLayout()
        for key, value in (report.get("parameters") or {}).items():
            parameters.addRow(str(key), QLabel(str(value)))
        if outputs:
            parameters.addRow("输出", QLabel("\n".join(outputs[:3])))
        layout.addLayout(parameters)

        tabs = QTabWidget()
        markdown_preview = QPlainTextEdit(str(report.get("cleaned_preview") or ""))
        markdown_preview.setReadOnly(True)
        markdown_preview.setPlaceholderText("没有可显示的 Markdown 预览。")
        tabs.addTab(markdown_preview, "清洗后 Markdown")

        outline = QTreeWidget()
        outline.setHeaderLabels(["标题结构", "级别", "行"])
        for heading in report.get("headings") or []:
            item = QTreeWidgetItem(
                [
                    ("　" * max(0, int(heading["level"]) - 1)) + str(heading["title"]),
                    f"H{heading['level']}",
                    str(heading["line"]),
                ]
            )
            outline.addTopLevelItem(item)
        outline.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tabs.addTab(outline, "标题结构")

        chunks = report.get("chunks") or []
        chunk_table = QTableWidget(len(chunks), 3)
        chunk_table.setHorizontalHeaderLabels(["顺序", "标题", "预计长度"])
        for row, chunk in enumerate(chunks):
            values = [chunk["index"], chunk["title"], f"{chunk['estimated_tokens']} tokens"]
            for column, value in enumerate(values):
                chunk_table.setItem(row, column, QTableWidgetItem(str(value)))
        chunk_table.horizontalHeader().setStretchLastSection(True)
        chunk_table.verticalHeader().setVisible(False)
        tabs.addTab(chunk_table, "文档拆分")

        ocr_pages = report.get("ocr_pages") or []
        ocr_table = QTableWidget(len(ocr_pages), 3)
        ocr_table.setHorizontalHeaderLabels(["页面/图片", "置信度", "状态"])
        for row, item in enumerate(ocr_pages):
            values = [
                item["label"],
                f"{float(item['confidence']):.1%}",
                "需要核对" if item.get("low_confidence") else "正常",
            ]
            for column, value in enumerate(values):
                ocr_table.setItem(row, column, QTableWidgetItem(str(value)))
        ocr_table.horizontalHeader().setStretchLastSection(True)
        ocr_table.verticalHeader().setVisible(False)
        tabs.addTab(ocr_table, "OCR")

        risk_list = QListWidget()
        risks = report.get("risks") or report.get("issues") or []
        if risks:
            for risk in risks:
                location = " · ".join(
                    part
                    for part in (
                        str(risk.get("source_label") or ""),
                        f"第 {risk['line']} 行" if risk.get("line") else "",
                    )
                    if part
                )
                location = f"{location} · " if location else ""
                risk_list.addItem(
                    f"[{str(risk.get('level') or risk.get('severity', 'info')).upper()}] "
                    f"{location}{risk['message']}"
                )
        else:
            risk_list.addItem("未发现明显风险。")
        tabs.addTab(risk_list, "风险提示")
        layout.addWidget(tabs)
        return page, (markdown_preview, outline, chunk_table, ocr_table, risk_list)

    def _context_pack_page(self, report: dict, outputs: list[str]) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.context_pack_summary = QLabel(
            f"完整性 {report.get('integrity', 'unknown')} · "
            f"约 {report.get('estimated_tokens', 0):,} tokens · "
            f"{report.get('source_count', 0)} 个来源 · "
            f"{report.get('pack_count', 0)} 个包"
        )
        self.context_pack_summary.setObjectName("previewSummary")
        layout.addWidget(self.context_pack_summary)
        form = QFormLayout()
        budget = report.get("requested_budget")
        form.addRow(
            "Context Budget",
            QLabel(f"{int(budget):,} 估算 tokens" if budget else "无限制"),
        )
        soft = report.get("soft_target")
        form.addRow("软目标", QLabel(f"{int(soft):,}" if soft else "—"))
        form.addRow("超出预算包数", QLabel(str(report.get("overflow_packs", 0))))
        form.addRow("完整性", QLabel(str(report.get("integrity", "未知"))))
        layout.addLayout(form)
        if outputs:
            output_label = QLabel("输出目录：\n" + "\n".join(outputs[:3]))
            output_label.setWordWrap(True)
            layout.addWidget(output_label)
        self.warning_list = QListWidget()
        for warning in report.get("warnings") or []:
            if isinstance(warning, dict):
                self.warning_list.addItem(
                    str(warning.get("reason") or warning.get("message") or warning)
                )
            else:
                self.warning_list.addItem(str(warning))
        if self.warning_list.count() == 0:
            self.warning_list.addItem("未发现警告。")
        layout.addWidget(QLabel("处理警告"))
        layout.addWidget(self.warning_list, 1)
        return page


class VideoPreviewDialog(QDialog):
    def __init__(self, previews: list[VideoPreview], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("视频处理预览（不会修改文件）")
        self.resize(1120, 520)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(len(previews), 12)
        self.table.setHorizontalHeaderLabels(
            [
                "文件",
                "拍摄时间",
                "时长",
                "分辨率",
                "帧率",
                "编码",
                "地点",
                "输出",
                "预计体积",
                "GPS",
                "设备",
                "元数据来源",
            ]
        )
        for row, preview in enumerate(previews):
            estimate = (
                "未知"
                if preview.estimated_size_max <= 0
                else f"{format_bytes(preview.estimated_size_min)} – "
                f"{format_bytes(preview.estimated_size_max)}"
            )
            values = [
                preview.source.name,
                preview.captured_at.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                f"{preview.duration_seconds:.1f} 秒",
                preview.resolution or "未知",
                f"{preview.frame_rate:.2f} fps" if preview.frame_rate else "未知",
                preview.codec or "未知",
                preview.location or "未提供",
                preview.output_name,
                estimate,
                (
                    f"{preview.latitude:.5f}, {preview.longitude:.5f}"
                    if preview.latitude is not None and preview.longitude is not None
                    else "无"
                ),
                preview.camera or "未知",
                (
                    f"{preview.metadata_source or '文件'} · "
                    f"时间：{preview.capture_time_source or '未知'}"
                ),
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        self.risk_list = QListWidget()
        for preview in previews:
            for risk in preview.risks:
                self.risk_list.addItem(
                    f"{preview.source.name} · [{risk.level.value.upper()}] {risk.message}"
                )
        if self.risk_list.count() == 0:
            self.risk_list.addItem("未发现明显风险。")
        layout.addWidget(QLabel("处理风险与提醒"))
        layout.addWidget(self.risk_list)
        layout.addWidget(QLabel("这是试运行预览；不会创建输出目录，也不会修改原文件。"))
        layout.addWidget(_close_buttons(self))


class SourcePlanDialog(QDialog):
    def __init__(
        self,
        title: str,
        sources: list[Path],
        parameters: dict[str, str],
        note: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 460)
        layout = QVBoxLayout(self)
        table = QTableWidget(len(sources), 3)
        table.setHorizontalHeaderLabels(["源文件", "类型", "体积"])
        for row, source in enumerate(sources):
            values = [
                source.name,
                source.suffix.lower() or "未知",
                format_bytes(source.stat().st_size),
            ]
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        layout.addWidget(table)
        form = QFormLayout()
        for key, value in parameters.items():
            form.addRow(key, QLabel(value))
        layout.addLayout(form)
        note_label = QLabel(note)
        note_label.setWordWrap(True)
        layout.addWidget(note_label)
        layout.addWidget(_close_buttons(self))


class ContactSheetPreviewDialog(QDialog):
    def __init__(self, source_name: str, image_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("联系表预览")
        self.resize(980, 720)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"来源：{source_name} · 联系表：{image_path.name}"))
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(image_path))
        if not pixmap.isNull():
            self.image_label.setPixmap(
                pixmap.scaled(
                    920,
                    620,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        layout.addWidget(self.image_label)
        layout.addWidget(_close_buttons(self))
