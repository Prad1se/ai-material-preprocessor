from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...application.preview_registry import PreviewRequest
from ...application.workspaces import WorkspaceId
from ...apps.documents.workspace_controller import DocumentWorkspaceController
from ...models import Operation, ToolStatus
from ...services.tool_capabilities import missing_feature_guidance
from .common import WorkspacePresentationState, WorkspaceView


class DocumentWorkspace(WorkspaceView):
    workspace_id = WorkspaceId.DOCUMENTS
    input_title = "Add documents"
    input_description = "PDF · Word · PowerPoint · Excel · HTML · TXT"
    input_accessible_description = "只接受文档格式；视频会建议转交 Video Workspace"

    def __init__(self, config: dict, tools: dict[str, ToolStatus], preview_registry) -> None:
        super().__init__(config, tools, DocumentWorkspaceController(tools), preview_registry)

    def _create_hero(self) -> QWidget:
        hero = QFrame()
        hero.setObjectName("documentHero")
        layout = QHBoxLayout(hero)
        copy = QVBoxLayout()
        eyebrow = QLabel("DORO DOCUMENTS  ·  LOCAL  ·  TRACEABLE")
        eyebrow.setObjectName("documentEyebrow")
        title = QLabel("Prepare documents for AI")
        title.setObjectName("title")
        subtitle = QLabel("安静、清晰地整理文档；当前继续使用稳定的 v2.0 转换与 OCR 能力。")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(subtitle)
        copy.addStretch()
        identity = QLabel("D")
        identity.setObjectName("documentIdentity")
        identity.setAlignment(Qt.AlignmentFlag.AlignCenter)
        identity.setAccessibleName("Doro Documents text identity placeholder")
        layout.addLayout(copy, 1)
        layout.addWidget(identity)
        return hero

    def _create_options_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 20, 22, 22)
        title = QLabel("Processing")
        title.setObjectName("sectionTitle")
        description = QLabel("这里只显示 Document operation 与文档参数")
        description.setObjectName("sectionDescription")
        self.tool_hint = QLabel()
        self.tool_hint.setObjectName("toolHint")
        self.tool_hint.setWordWrap(True)
        self.operation = QComboBox()
        self.operation.currentIndexChanged.connect(self._operation_changed)
        self.document_mode = QComboBox()
        self.document_mode.addItem("AI 增强 · 清洗、质检并可拆分", "enhanced")
        self.document_mode.addItem("原始转换 · 仅保留 MarkItDown 结果", "raw")
        self.document_mode.setCurrentIndex(
            1 if str(self.config["document"]["mode"]) == "raw" else 0
        )
        self.document_mode.currentIndexChanged.connect(self._operation_changed)
        self.split_document = QCheckBox("按 AI 易读长度自动拆分")
        self.split_document.setChecked(bool(self.config["document"]["split_enabled"]))
        self.target_tokens = QSpinBox()
        self.target_tokens.setRange(500, 100000)
        self.target_tokens.setSingleStep(500)
        self.target_tokens.setSuffix(" 估算 tokens / 段")
        self.target_tokens.setValue(int(self.config["document"]["target_tokens"]))
        self.ocr_enabled = QCheckBox("使用本地 OCR 识别扫描页和内嵌图片（较慢）")
        self.ocr_enabled.setChecked(bool(self.config["document"]["ocr_enabled"]))
        self.preview_button = QPushButton("预览文档处理方案")
        self.preview_button.setObjectName("secondary")
        self.preview_button.clicked.connect(self._show_preview)
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("默认：原文件旁的“AI素材处理结果”")
        output_button = QPushButton("选择…")
        output_button.setObjectName("secondary")
        output_button.clicked.connect(self._choose_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_path)
        output_row.addWidget(output_button)
        self.output_hint = QLabel()
        self.output_hint.setObjectName("outputHint")
        self.output_hint.setWordWrap(True)
        for widget in (
            title,
            description,
            self.tool_hint,
            self.operation,
            self.document_mode,
            self.split_document,
            self.target_tokens,
            self.ocr_enabled,
            self.preview_button,
        ):
            layout.addWidget(widget)
        layout.addWidget(QLabel("保存到"))
        layout.addLayout(output_row)
        layout.addWidget(self.output_hint)
        layout.addStretch()
        return panel

    def _choose_output(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path = QFileDialog.getExistingDirectory(self, "选择文档输出目录")
        if path:
            self.output_path.setText(path)

    def refresh_operations(self) -> None:
        previous = self.operation.currentData()
        common = self.controller.operations_for(self.paths)
        self.operation.blockSignals(True)
        self.operation.clear()
        for operation in common:
            self.operation.addItem(operation.value, operation.value)
        if previous is not None:
            index = self.operation.findData(previous)
            if index >= 0:
                self.operation.setCurrentIndex(index)
        self.operation.blockSignals(False)
        self.start_button.setEnabled(bool(self.paths and common))
        guidance = missing_feature_guidance(self.paths[0].suffix, self.tools) if self.paths else ""
        self.tool_hint.setText(guidance)
        self.tool_hint.setVisible(bool(guidance))
        ocr = self.tools.get("rapidocr", ToolStatus("rapidocr", None)).available
        self.ocr_enabled.setEnabled(ocr)
        self._operation_changed()

    def _operation_changed(self) -> None:
        raw = self.operation.currentData()
        markdown = raw == Operation.TO_MARKDOWN.value
        enhanced = markdown and self.document_mode.currentData() == "enhanced"
        self.document_mode.setVisible(markdown)
        self.split_document.setVisible(enhanced)
        self.target_tokens.setVisible(enhanced)
        self.ocr_enabled.setVisible(enhanced)
        self.preview_button.setVisible(raw is not None)
        if raw is None:
            self.output_hint.setText("添加文档后显示输出说明。")
        elif markdown and enhanced:
            self.output_hint.setText("输出：现有 AI 资料包格式；本阶段没有加入新的 Context Pack。")
        elif markdown:
            self.output_hint.setText("输出：单个 Markdown 文件。")
        else:
            self.output_hint.setText("输出：单个 PDF 文件。")

    def _parameters(self) -> dict[str, object]:
        enhanced = self.document_mode.currentData() == "enhanced"
        return {
            "模式": "AI 增强" if enhanced else "原始转换",
            "自动拆分": "是" if enhanced and self.split_document.isChecked() else "否",
            "目标长度": f"{self.target_tokens.value()} tokens",
            "OCR": "开启"
            if enhanced and self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
            else "关闭",
        }

    def _show_preview(self) -> None:
        if not self.paths or self.operation.currentData() is None:
            return
        operation = Operation(self.operation.currentData())
        request = PreviewRequest(
            tuple(self.paths), operation, self.output_for(self.paths[0]), self._parameters()
        )
        try:
            self.preview_ready.emit(self.preview_registry.build(request))
            self.set_presentation_state(WorkspacePresentationState.PREVIEW)
        except Exception as exc:
            QMessageBox.critical(self, "无法生成预览", str(exc))

    def _request_jobs(self) -> None:
        if not self.paths or self.operation.currentData() is None:
            return
        operation = Operation(self.operation.currentData())
        self.config["document"]["mode"] = str(self.document_mode.currentData())
        self.config["document"]["split_enabled"] = self.split_document.isChecked()
        self.config["document"]["target_tokens"] = self.target_tokens.value()
        self.config["document"]["max_tokens"] = max(
            self.target_tokens.value() + 1000,
            int(self.config["document"].get("max_tokens", 6000)),
        )
        self.config["document"]["ocr_enabled"] = (
            self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
        )
        jobs = self.controller.create_jobs(self.paths, operation, self.output_for)
        self.jobs_requested.emit(self.workspace_id.value, jobs)
