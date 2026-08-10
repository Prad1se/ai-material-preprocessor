from __future__ import annotations

import os
import sys
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .capabilities import available_operations
from .models import Job, Operation, ToolStatus
from .services.config import load_config, save_config
from .services.environment import detect_tools
from .services.metadata import read_media_metadata
from .services.naming import preview_video_rename
from .services.task_manifest import (
    clear_history,
    history_usage,
    resolve_history_root,
)
from .ui.theme import APP_STYLESHEET
from .ui.workers import Worker

MOUSE_STATE_ASSETS = {
    "idle": "mouse-grin.png",
    "thinking": "mouse-thinking.png",
    "working": "mouse-thinking.png",
    "success": "mouse-strong.png",
    "error": "mouse-thinking.png",
}


def mouse_asset_path(filename: str) -> Path:
    """Resolve a mascot asset in source and PyInstaller onedir builds."""
    packaged = Path(getattr(sys, "_MEIPASS", Path.cwd())) / "assets" / "mouse" / filename
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[2] / "assets" / "mouse" / filename


class DropList(QListWidget):
    files_added = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)
        self.setToolTip("把文件拖到这里")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and Path(url.toLocalFile()).is_file()
        ]
        if paths:
            self.files_added.emit(paths)
            event.acceptProposedAction()


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        config: dict | None = None,
        tools: dict[str, ToolStatus] | None = None,
    ) -> None:
        super().__init__()
        self.config = config or load_config()
        self.tools = tools or detect_tools(self.config)
        self.paths: list[Path] = []
        self.worker: Worker | None = None
        self.last_outputs: list[str] = []

        self.setWindowTitle("AI 素材预处理工具")
        self.resize(1120, 780)
        self.setMinimumSize(900, 680)
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("page")
        root = QVBoxLayout(central)
        root.setContentsMargins(46, 34, 46, 40)
        root.setSpacing(20)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(30, 24, 26, 22)
        hero_layout.setSpacing(20)
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(8)
        eyebrow = QLabel("LOCAL  ·  PRIVATE  ·  鼠鼠不碰原文件")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("鼠鼠帮你把素材，\n准备成下一步需要的样子。")
        title.setObjectName("title")
        subtitle = QLabel(
            "交给 AI、普通转换、准备创作都在这里完成。处理全程留在本机，原文件始终保留。"
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        hero_copy.addWidget(eyebrow)
        hero_copy.addWidget(title)
        hero_copy.addWidget(subtitle)
        hero_copy.addStretch()
        self.mouse_mascot = QLabel()
        self.mouse_mascot.setObjectName("mouseMascot")
        self.mouse_mascot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mouse_mascot.setFixedSize(230, 210)
        hero_layout.addLayout(hero_copy, 1)
        hero_layout.addWidget(self.mouse_mascot)
        root.addWidget(hero)

        workflow = QHBoxLayout()
        workflow.setSpacing(10)
        for index, label in enumerate(("1  选择素材", "2  识别能力", "3  鼠鼠处理", "4  保存结果")):
            step = QLabel(label)
            step.setObjectName("workflowActive" if index == 0 else "workflowStep")
            step.setAlignment(Qt.AlignmentFlag.AlignCenter)
            workflow.addWidget(step)
        root.addLayout(workflow)

        content_row = QHBoxLayout()
        content_row.setSpacing(18)

        files_frame = QFrame()
        files_frame.setObjectName("panel")
        files_layout = QVBoxLayout(files_frame)
        files_layout.setContentsMargins(24, 22, 24, 24)
        files_layout.setSpacing(14)
        file_header = QHBoxLayout()
        file_title = QLabel("把文件交给鼠鼠")
        file_title.setObjectName("sectionTitle")
        add_button = QPushButton("选择文件…")
        add_button.setObjectName("secondary")
        add_button.clicked.connect(self._choose_files)
        clear_button = QPushButton("清空")
        clear_button.setObjectName("secondary")
        clear_button.clicked.connect(self._clear_files)
        file_header.addWidget(file_title)
        file_header.addStretch()
        file_header.addWidget(add_button)
        file_header.addWidget(clear_button)
        file_description = QLabel("拖入 Word、PPT、Excel、PDF、网页或视频；鼠鼠会自动判断可用操作")
        file_description.setObjectName("sectionDescription")
        self.file_list = DropList()
        self.file_list.setObjectName("dropZone")
        self.file_list.setMinimumHeight(280)
        self.file_list.files_added.connect(self._add_files)
        self.file_list.setAccessibleDescription("拖入 Word、PPT、Excel、PDF、HTML 或视频文件")
        files_layout.addLayout(file_header)
        files_layout.addWidget(file_description)
        files_layout.addWidget(self.file_list)
        content_row.addWidget(files_frame, 5)

        options_frame = QFrame()
        options_frame.setObjectName("panel")
        options_layout = QVBoxLayout(options_frame)
        options_layout.setContentsMargins(24, 22, 24, 24)
        options_layout.setSpacing(12)
        options_title = QLabel("鼠鼠要做什么")
        options_title.setObjectName("sectionTitle")
        options_description = QLabel("只显示当前素材真正可用的操作")
        options_description.setObjectName("sectionDescription")
        self.operation = QComboBox()
        self.operation.currentIndexChanged.connect(self._operation_changed)
        self.document_mode = QComboBox()
        self.document_mode.addItem("AI 增强 · 清洗、质检并可拆分", "enhanced")
        self.document_mode.addItem("原始转换 · 仅保留 MarkItDown 结果", "raw")
        configured_mode = str(self.config["document"]["mode"])
        self.document_mode.setCurrentIndex(1 if configured_mode == "raw" else 0)
        self.document_mode.currentIndexChanged.connect(self._operation_changed)
        self.split_document = QCheckBox("按 AI 易读长度自动拆分")
        self.split_document.setChecked(bool(self.config["document"]["split_enabled"]))
        self.target_tokens = QSpinBox()
        self.target_tokens.setRange(500, 100000)
        self.target_tokens.setSingleStep(500)
        self.target_tokens.setSuffix(" 估算 tokens / 段")
        self.target_tokens.setValue(int(self.config["document"]["target_tokens"]))
        self.target_tokens.setToolTip("默认 4000；这是跨模型的保守估算，不是特定模型的精确计数。")
        self.ocr_enabled = QCheckBox("使用本地 OCR 识别扫描页和内嵌图片（较慢）")
        self.ocr_enabled.setChecked(bool(self.config["document"]["ocr_enabled"]))
        ocr_available = self.tools.get("rapidocr", ToolStatus("rapidocr", None)).available
        self.ocr_enabled.setEnabled(ocr_available)
        if not ocr_available:
            self.ocr_enabled.setToolTip("当前发布包未检测到 RapidOCR。普通转换和 AI 增强仍可使用。")
        self.quality = QComboBox()
        self.quality.addItem("高质量 · 文件较大（CRF 20）", 20)
        self.quality.addItem("均衡（CRF 23）", 23)
        self.quality.addItem("体积优先（CRF 28）", 28)
        configured_crf = int(self.config["video"]["compression_crf"])
        for index in range(self.quality.count()):
            if self.quality.itemData(index) == configured_crf:
                self.quality.setCurrentIndex(index)
                break
        self.audio_format = QComboBox()
        self.audio_format.addItem("MP3 · 兼容且体积小", "mp3")
        self.audio_format.addItem("WAV · 无损且适合剪辑", "wav")
        configured_audio = str(self.config["video"]["audio_format"]).lower()
        self.audio_format.setCurrentIndex(1 if configured_audio == "wav" else 0)
        self.scene_sensitivity = QComboBox()
        self.scene_sensitivity.addItem("关键帧：更多场景（灵敏度高）", 0.20)
        self.scene_sensitivity.addItem("关键帧：均衡", 0.30)
        self.scene_sensitivity.addItem("关键帧：只保留明显变化", 0.45)
        configured_threshold = float(self.config["video"]["scene_threshold"])
        self.scene_sensitivity.setCurrentIndex(
            min(
                range(self.scene_sensitivity.count()),
                key=lambda i: abs(float(self.scene_sensitivity.itemData(i)) - configured_threshold),
            )
        )
        self.max_keyframes = QSpinBox()
        self.max_keyframes.setRange(4, 60)
        self.max_keyframes.setSuffix(" 张关键帧上限")
        self.max_keyframes.setValue(int(self.config["video"]["max_keyframes"]))
        self.location = QLineEdit()
        self.location.setPlaceholderText("地点（可选；优先于视频元数据，例如：杭州西湖）")
        self.rename_template = QLineEdit(str(self.config["video"]["rename_template"]))
        self.rename_template.setPlaceholderText("命名模板：{date}_{time}_{location}_{index}")
        self.rename_template.setToolTip(
            "支持日期时间、地点、坐标、分辨率、时长、编码、相机和原文件名等字段。"
        )
        self.preview_button = QPushButton("预览新文件名")
        self.preview_button.setObjectName("secondary")
        self.preview_button.clicked.connect(self._show_rename_preview)
        output_row = QHBoxLayout()
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("默认：原文件旁的“AI素材处理结果”")
        output_button = QPushButton("选择…")
        output_button.setObjectName("secondary")
        output_button.clicked.connect(self._choose_output)
        output_row.addWidget(self.output_path)
        output_row.addWidget(output_button)
        options_layout.addWidget(options_title)
        options_layout.addWidget(options_description)
        options_layout.addWidget(self.operation)
        options_layout.addWidget(self.document_mode)
        options_layout.addWidget(self.split_document)
        options_layout.addWidget(self.target_tokens)
        options_layout.addWidget(self.ocr_enabled)
        options_layout.addWidget(self.quality)
        options_layout.addWidget(self.audio_format)
        options_layout.addWidget(self.scene_sensitivity)
        options_layout.addWidget(self.max_keyframes)
        options_layout.addWidget(self.location)
        options_layout.addWidget(self.rename_template)
        options_layout.addWidget(self.preview_button)
        output_label = QLabel("保存到")
        output_label.setObjectName("fieldLabel")
        options_layout.addSpacing(6)
        options_layout.addWidget(output_label)
        options_layout.addLayout(output_row)
        self.output_hint = QLabel()
        self.output_hint.setObjectName("outputHint")
        self.output_hint.setWordWrap(True)
        options_layout.addWidget(self.output_hint)
        options_layout.addStretch()
        content_row.addWidget(options_frame, 4)
        root.addLayout(content_row)

        action_row = QHBoxLayout()
        self.start_button = QPushButton("开始处理")
        self.start_button.setObjectName("primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._start)
        self.open_button = QPushButton("打开结果")
        self.open_button.setObjectName("secondary")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_output)
        action_row.addWidget(self.start_button, 2)
        action_row.addWidget(self.open_button, 1)
        root.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.status = QLabel("等待文件")
        self.status.setObjectName("status")
        root.addWidget(self.progress)
        root.addWidget(self.status)

        history_frame = QFrame()
        history_frame.setObjectName("historyBar")
        history_layout = QHBoxLayout(history_frame)
        history_layout.setContentsMargins(16, 10, 12, 10)
        self.history_label = QLabel("处理历史统一保存在应用数据目录，不会出现在导出文件中。")
        self.history_label.setObjectName("historyLabel")
        self.history_label.setToolTip(str(resolve_history_root(self.config)))
        self.history_button = QPushButton("查看历史记录")
        self.history_button.setObjectName("linkButton")
        self.history_button.clicked.connect(self._open_history)
        self.clear_history_button = QPushButton("清除历史")
        self.clear_history_button.setObjectName("dangerLinkButton")
        self.clear_history_button.clicked.connect(self._clear_history)
        history_layout.addWidget(self.history_label)
        history_layout.addStretch()
        history_layout.addWidget(self.history_button)
        history_layout.addWidget(self.clear_history_button)
        root.addWidget(history_frame)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)
        self._set_mouse_state("idle")
        self._operation_changed()

    def _set_mouse_state(self, state: str) -> None:
        state = state if state in MOUSE_STATE_ASSETS else "idle"
        pixmap = QPixmap(str(mouse_asset_path(MOUSE_STATE_ASSETS[state])))
        if not pixmap.isNull():
            self.mouse_mascot.setPixmap(
                pixmap.scaled(
                    self.mouse_mascot.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.mouse_mascot.setProperty("state", state)

    def _apply_style(self) -> None:
        self.setStyleSheet(APP_STYLESHEET)

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择素材文件")
        self._add_files(paths)

    def _add_files(self, paths: list[str]) -> None:
        known = {str(path).lower() for path in self.paths}
        for raw_path in paths:
            path = Path(raw_path).resolve()
            if path.is_file() and str(path).lower() not in known:
                self.paths.append(path)
                self.file_list.addItem(str(path))
                known.add(str(path).lower())
        if self.paths:
            self._refresh_operations()
            self._set_mouse_state("thinking")

    def _clear_files(self) -> None:
        self.paths.clear()
        self.file_list.clear()
        self._refresh_operations()
        self.status.setText("等待文件")
        self._set_mouse_state("idle")

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.output_path.setText(path)

    def _operation_changed(self) -> None:
        raw_operation = self.operation.currentData()
        if raw_operation is None:
            self.document_mode.setVisible(False)
            self.split_document.setVisible(False)
            self.target_tokens.setVisible(False)
            self.ocr_enabled.setVisible(False)
            self.quality.setVisible(False)
            self.audio_format.setVisible(False)
            self.scene_sensitivity.setVisible(False)
            self.max_keyframes.setVisible(False)
            self.location.setVisible(False)
            self.rename_template.setVisible(False)
            self.preview_button.setVisible(False)
            self.output_hint.setText("添加素材后，这里会说明最终生成单个文件还是资料包。")
            return
        operation = Operation(raw_operation)
        markdown = operation == Operation.TO_MARKDOWN
        enhanced = markdown and self.document_mode.currentData() == "enhanced"
        self.document_mode.setVisible(markdown)
        self.split_document.setVisible(enhanced)
        self.target_tokens.setVisible(enhanced)
        self.ocr_enabled.setVisible(enhanced)
        renaming = operation == Operation.RENAME_VIDEO
        self.quality.setVisible(operation == Operation.COMPRESS_VIDEO)
        self.audio_format.setVisible(operation == Operation.EXTRACT_AUDIO)
        storyboard = operation == Operation.KEYFRAMES_CONTACT_SHEET
        self.scene_sensitivity.setVisible(storyboard)
        self.max_keyframes.setVisible(storyboard)
        self.location.setVisible(renaming)
        self.rename_template.setVisible(renaming)
        self.preview_button.setVisible(renaming)
        if markdown and enhanced:
            self.output_hint.setText(
                "输出：一个精简 AI 资料包，包含清洗正文、按需拆分内容和 manifest.json；完成后弹窗显示质量检查。"
            )
        elif markdown:
            self.output_hint.setText("输出：单个 Markdown 文件，直接保存在所选目录。")
        elif operation == Operation.TO_PDF:
            self.output_hint.setText("输出：单个 PDF 文件，直接保存在所选目录。")
        elif operation == Operation.KEYFRAMES_CONTACT_SHEET:
            self.output_hint.setText(
                "输出：一个关键帧包文件夹，包含联系表、关键帧与 manifest.json。"
            )
        else:
            self.output_hint.setText("输出：单个处理结果文件，直接保存在所选目录。")
        hint = ""
        if (
            operation
            in {
                Operation.COMPRESS_VIDEO,
                Operation.EXTRACT_AUDIO,
                Operation.STANDARDIZE_MP4,
                Operation.KEYFRAMES_CONTACT_SHEET,
            }
            and not self.tools.get("ffmpeg", ToolStatus("ffmpeg", None)).available
        ):
            hint = "（需要安装 FFmpeg）"
        elif operation == Operation.RENAME_VIDEO and not any(
            self.tools.get(name, ToolStatus(name, None)).available
            for name in ("exiftool", "ffprobe", "ffmpeg")
        ):
            hint = "（未发现元数据工具，将使用文件时间；可手动填写地点）"
        self.status.setText(operation.value + hint)

    def _refresh_operations(self) -> None:
        previous = self.operation.currentData()
        self.operation.blockSignals(True)
        self.operation.clear()
        common: list[Operation] = []
        if self.paths:
            operation_sets = [set(available_operations(path, self.tools)) for path in self.paths]
            allowed = set.intersection(*operation_sets) if operation_sets else set()
            common = [operation for operation in Operation if operation in allowed]
            for operation in common:
                self.operation.addItem(operation.value, operation.value)
        if previous is not None:
            for index in range(self.operation.count()):
                if self.operation.itemData(index) == previous:
                    self.operation.setCurrentIndex(index)
                    break
        self.operation.blockSignals(False)
        self.start_button.setEnabled(bool(self.paths and common and self.worker is None))
        if self.paths and not common:
            self.status.setText("所选文件没有共同可执行的操作，请按文档或视频分批处理。")
        elif self.paths:
            self.status.setText(f"已添加 {len(self.paths)} 个文件；请选择处理方式。")
        self._operation_changed()

    def _show_rename_preview(self) -> None:
        if not self.paths:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("新文件名预览（不会修改原文件）")
        dialog.resize(820, 360)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(self.paths), 4)
        table.setHorizontalHeaderLabels(["原文件", "拍摄时间", "地点", "输出文件"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        for index, source in enumerate(self.paths, start=1):
            metadata = read_media_metadata(
                source,
                self.tools["exiftool"].path,
                self.tools["ffprobe"].path,
                ffmpeg=self.tools["ffmpeg"].path,
            )
            destination = self._job_output(source)
            preview = preview_video_rename(
                source,
                destination,
                metadata,
                self.rename_template.text().strip() or "{date}_{time}_{location}_{index}",
                index,
                self.location.text(),
            )
            values = [
                source.name,
                metadata.captured_at.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                metadata.effective_location(self.location.text()) or "未提供",
                preview.output.name,
            ]
            for column, value in enumerate(values):
                table.setItem(index - 1, column, QTableWidgetItem(value))
        layout.addWidget(table)
        note = QLabel("预览仅读取元数据；正式处理会复制到独立目录，原文件不改名。")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _job_output(self, source: Path) -> Path:
        explicit = self.output_path.text().strip()
        if explicit:
            return Path(explicit).resolve()
        return source.parent / str(self.config["output_folder_name"])

    def _start(self) -> None:
        if not self.paths:
            QMessageBox.information(self, "还没有文件", "请先添加至少一个文件。")
            return
        if self.operation.currentData() is None:
            return
        operation = Operation(self.operation.currentData())
        self.config["video"]["compression_crf"] = int(self.quality.currentData())
        self.config["video"]["audio_format"] = str(self.audio_format.currentData())
        self.config["video"]["rename_template"] = (
            self.rename_template.text().strip() or "{date}_{time}_{location}_{index}"
        )
        self.config["video"]["scene_threshold"] = float(self.scene_sensitivity.currentData())
        self.config["video"]["max_keyframes"] = int(self.max_keyframes.value())
        self.config["document"]["mode"] = str(self.document_mode.currentData())
        self.config["document"]["split_enabled"] = self.split_document.isChecked()
        self.config["document"]["target_tokens"] = int(self.target_tokens.value())
        self.config["document"]["max_tokens"] = max(
            int(self.target_tokens.value()) + 1000,
            int(self.config["document"].get("max_tokens", 6000)),
        )
        self.config["document"]["ocr_enabled"] = (
            self.ocr_enabled.isEnabled() and self.ocr_enabled.isChecked()
        )
        with suppress(OSError):
            save_config(self.config)
        jobs = [
            Job(
                source=path,
                operation=operation,
                output_root=self._job_output(path),
                location=self.location.text(),
            )
            for path in self.paths
        ]
        self.start_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.progress.setValue(0)
        self._set_mouse_state("working")
        self.worker = Worker(jobs, self.tools, self.config)
        self.worker.progress.connect(self._on_progress)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failure)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _on_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.status.setText(message)
        self._set_mouse_state("working")

    @staticmethod
    def _quality_report_text(reports: list[dict], outputs: list[str]) -> str:
        sections: list[str] = []
        for report in reports:
            sections.append(
                f"{report['source']}\n"
                f"质量分：{report['score']}/100    "
                f"估算长度：{report['estimated_tokens']} tokens\n"
                f"标题：{report['heading_count']}    图片：{report['image_count']}"
            )
            issues = report.get("issues") or []
            if issues:
                sections.append(
                    "需要注意：\n" + "\n".join(f"• {issue['message']}" for issue in issues[:6])
                )
            else:
                sections.append("未发现明显问题。")
        if outputs:
            sections.append("输出位置：\n" + "\n".join(outputs[:3]))
        return "\n\n".join(sections)

    def _on_completed(
        self, outputs: list[str], errors: list[str], quality_reports: list[dict]
    ) -> None:
        self.last_outputs = outputs
        self._set_mouse_state("success" if outputs else "error")
        self.open_button.setEnabled(bool(outputs))
        if quality_reports:
            message = self._quality_report_text(quality_reports, outputs)
            if errors:
                message += "\n\n未完成：\n" + "\n".join(errors[:6])
                QMessageBox.warning(self, "转换完成与质量检查", message)
            else:
                QMessageBox.information(self, "转换质量检查", message)
            self.status.setText(
                f"处理完成：已生成 {len(outputs)} 项；质量检查已显示，原文件未改动。"
            )
            return
        if errors:
            self.status.setText(
                f"处理结束：成功 {len(outputs)} 个，失败 {len(errors)} 个；原文件未改动。"
            )
            QMessageBox.warning(
                self,
                "部分任务未完成",
                "成功生成：" + str(len(outputs)) + "\n\n" + "\n".join(errors[:8]),
            )
        else:
            self.status.setText(f"处理完成：已生成 {len(outputs)} 个文件，原文件未改动。")
            QMessageBox.information(
                self,
                "处理完成",
                "已生成：\n" + "\n".join(outputs[:5]) + ("\n…" if len(outputs) > 5 else ""),
            )

    def _worker_finished(self) -> None:
        self.worker = None
        self._refresh_operations()

    def _on_failure(self, message: str) -> None:
        self.status.setText("处理失败；原文件未改动。")
        self._set_mouse_state("error")
        QMessageBox.critical(self, "处理失败", message)

    def _open_output(self) -> None:
        if not self.last_outputs:
            return
        folder = str(Path(self.last_outputs[0]).parent)
        if os.name == "nt":
            os.startfile(folder)

    def _open_history(self) -> None:
        history = resolve_history_root(self.config)
        history.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(history))

    @staticmethod
    def _format_bytes(value: int) -> str:
        size = float(value)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    def _clear_history(self) -> None:
        history = resolve_history_root(self.config)
        usage = history_usage(history)
        if usage.task_count == 0 and usage.total_bytes == 0:
            QMessageBox.information(self, "没有历史记录", "当前没有可清除的处理历史。")
            return
        answer = QMessageBox.question(
            self,
            "清除全部历史记录？",
            f"将永久删除 {usage.task_count} 条记录，约 {self._format_bytes(usage.total_bytes)}。\n\n"
            "这不会删除任何原文件或转换结果，但历史记录无法恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = clear_history(history)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "清除失败", str(exc))
            return
        self.status.setText(f"已清除 {removed.task_count} 条历史记录。")
        QMessageBox.information(
            self,
            "历史记录已清除",
            f"已永久删除 {removed.task_count} 条记录，释放 {self._format_bytes(removed.total_bytes)}。",
        )


def launch_for_smoke_test() -> MainWindow:
    """Build a window without starting the event loop."""
    if QApplication.instance() is None:
        QApplication([])
    return MainWindow()
