from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
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
from ...apps.video.workspace_controller import VideoWorkspaceController
from ...models import Operation, ToolStatus
from ..mascot import MOUSE_STATE_ASSETS, mouse_asset_path
from .common import WorkspacePresentationState, WorkspaceView


class VideoWorkspace(WorkspaceView):
    workspace_id = WorkspaceId.VIDEO
    input_title = "Media Queue"
    input_description = "MP4 · MOV · MKV · AVI · WebM · M4V"
    input_accessible_description = "只接受视频格式；文档会建议转交 Documents Workspace"

    def __init__(self, config: dict, tools: dict[str, ToolStatus], preview_registry) -> None:
        super().__init__(config, tools, VideoWorkspaceController(tools), preview_registry)
        self.set_mouse_state("idle")

    def _create_hero(self) -> QWidget:
        hero = QFrame()
        hero.setObjectName("videoHero")
        layout = QHBoxLayout(hero)
        copy = QVBoxLayout()
        eyebrow = QLabel("鼠鼠 VIDEO  ·  MEDIA WORKSHOP")
        eyebrow.setObjectName("videoEyebrow")
        title = QLabel("鼠鼠 Video Workshop")
        title.setObjectName("title")
        subtitle = QLabel("压缩、标准化、音频、关键帧与素材整理继续使用稳定的 v2.0 工作流。")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(subtitle)
        copy.addStretch()
        self.mouse_mascot = QLabel()
        self.mouse_mascot.setObjectName("mouseMascot")
        self.mouse_mascot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mouse_mascot.setFixedSize(190, 160)
        layout.addLayout(copy, 1)
        layout.addWidget(self.mouse_mascot)
        return hero

    def _create_options_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 20, 22, 22)
        title = QLabel("Actions")
        title.setObjectName("sectionTitle")
        description = QLabel("这里只显示 Video operation 与媒体参数")
        description.setObjectName("sectionDescription")
        self.operation = QComboBox()
        self.operation.currentIndexChanged.connect(self._operation_changed)
        self.quality = QComboBox()
        self.quality.addItem("高质量 · CRF 20", 20)
        self.quality.addItem("均衡 · CRF 23", 23)
        self.quality.addItem("体积优先 · CRF 28", 28)
        self.quality.setCurrentIndex(
            max(0, self.quality.findData(int(self.config["video"]["compression_crf"])))
        )
        self.audio_format = QComboBox()
        self.audio_format.addItem("MP3 · 兼容且体积小", "mp3")
        self.audio_format.addItem("WAV · 无损且适合剪辑", "wav")
        self.audio_format.setCurrentIndex(
            max(0, self.audio_format.findData(str(self.config["video"]["audio_format"])))
        )
        self.scene_sensitivity = QComboBox()
        self.scene_sensitivity.addItem("关键帧：更多场景", 0.20)
        self.scene_sensitivity.addItem("关键帧：均衡", 0.30)
        self.scene_sensitivity.addItem("关键帧：明显变化", 0.45)
        self.scene_sensitivity.setCurrentIndex(
            min(
                range(self.scene_sensitivity.count()),
                key=lambda index: abs(
                    float(self.scene_sensitivity.itemData(index))
                    - float(self.config["video"]["scene_threshold"])
                ),
            )
        )
        self.max_keyframes = QSpinBox()
        self.max_keyframes.setRange(4, 60)
        self.max_keyframes.setSuffix(" 张关键帧上限")
        self.max_keyframes.setValue(int(self.config["video"]["max_keyframes"]))
        self.location = QLineEdit()
        self.location.setPlaceholderText("地点（可选）")
        self.project_name = QLineEdit(str(self.config["video"].get("project_name", "")))
        self.project_name.setPlaceholderText("项目名称（可选）")
        self.organize_mode = QComboBox()
        self.organize_mode.addItem("按日期和地点分层", "date_location")
        self.organize_mode.addItem("只按日期分层", "date")
        self.organize_mode.addItem("只按地点分层", "location")
        self.organize_mode.setCurrentIndex(
            max(
                0,
                self.organize_mode.findData(
                    str(self.config["video"].get("organize_mode", "date_location"))
                ),
            )
        )
        self.rename_template = QLineEdit(str(self.config["video"]["rename_template"]))
        self.preview_button = QPushButton("预览视频处理方案")
        self.preview_button.setObjectName("secondary")
        self.preview_button.clicked.connect(self._show_preview)
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("默认：原视频旁的“AI素材处理结果”")
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
            self.operation,
            self.quality,
            self.audio_format,
            self.scene_sensitivity,
            self.max_keyframes,
            self.location,
            self.project_name,
            self.organize_mode,
            self.rename_template,
            self.preview_button,
        ):
            layout.addWidget(widget)
        layout.addWidget(QLabel("保存到"))
        layout.addLayout(output_row)
        layout.addWidget(self.output_hint)
        layout.addStretch()
        return panel

    def set_mouse_state(self, state: str) -> None:
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

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择视频输出目录")
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
        self._operation_changed()

    def _operation_changed(self) -> None:
        raw = self.operation.currentData()
        operation = Operation(raw) if raw is not None else None
        renaming = operation in {Operation.RENAME_VIDEO, Operation.ORGANIZE_VIDEO}
        self.quality.setVisible(operation is Operation.COMPRESS_VIDEO)
        self.audio_format.setVisible(operation is Operation.EXTRACT_AUDIO)
        storyboard = operation is Operation.KEYFRAMES_CONTACT_SHEET
        self.scene_sensitivity.setVisible(storyboard)
        self.max_keyframes.setVisible(storyboard)
        self.location.setVisible(renaming)
        self.project_name.setVisible(renaming)
        self.organize_mode.setVisible(operation is Operation.ORGANIZE_VIDEO)
        self.rename_template.setVisible(renaming)
        self.preview_button.setVisible(operation is not None)
        if operation is Operation.KEYFRAMES_CONTACT_SHEET:
            self.output_hint.setText("输出：现有关键帧包、联系表与 manifest.json。")
        elif operation is Operation.ORGANIZE_VIDEO:
            self.output_hint.setText("输出：按日期/地点生成副本；原视频不移动、不改名。")
        elif operation is None:
            self.output_hint.setText("添加视频后显示输出说明。")
        else:
            self.output_hint.setText("输出：单个媒体处理结果。")

    def _parameters(self, operation: Operation) -> dict[str, object]:
        if operation is Operation.COMPRESS_VIDEO:
            return {
                "compression_crf": int(self.quality.currentData()),
                "compression_preset": str(self.config["video"]["compression_preset"]),
            }
        if operation is Operation.EXTRACT_AUDIO:
            return {
                "audio_format": str(self.audio_format.currentData()),
                "audio_bitrate": str(self.config["video"]["audio_bitrate"]),
            }
        if operation is Operation.KEYFRAMES_CONTACT_SHEET:
            return {
                "scene_threshold": float(self.scene_sensitivity.currentData()),
                "max_keyframes": self.max_keyframes.value(),
                "columns": int(self.config["video"]["contact_sheet_columns"]),
            }
        if operation in {Operation.RENAME_VIDEO, Operation.ORGANIZE_VIDEO}:
            return {
                "rename_template": self.rename_template.text().strip()
                or "{date}_{time}_{location}_{index}",
                "project_name": self.project_name.text().strip(),
                "organize_mode": str(self.organize_mode.currentData()),
                "location_dictionary": dict(self.config["video"].get("location_dictionary", {})),
            }
        return {"输出编码": "H.264 / AAC", "容器": "MP4"}

    def _tool_paths(self) -> dict[str, str]:
        return {
            name: status.path
            for name in ("ffmpeg", "ffprobe", "exiftool")
            if (status := self.tools.get(name)) is not None and status.path
        }

    def _show_preview(self) -> None:
        if not self.paths or self.operation.currentData() is None:
            return
        operation = Operation(self.operation.currentData())
        request = PreviewRequest(
            tuple(self.paths),
            operation,
            self.output_for(self.paths[0]),
            self._parameters(operation),
            self._tool_paths(),
            self.location.text(),
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
        self.config["video"].update(
            {
                "compression_crf": int(self.quality.currentData()),
                "audio_format": str(self.audio_format.currentData()),
                "rename_template": self.rename_template.text().strip()
                or "{date}_{time}_{location}_{index}",
                "project_name": self.project_name.text().strip(),
                "organize_mode": str(self.organize_mode.currentData()),
                "scene_threshold": float(self.scene_sensitivity.currentData()),
                "max_keyframes": self.max_keyframes.value(),
            }
        )
        jobs = self.controller.create_jobs(
            self.paths,
            operation,
            self.output_for,
            location=self.location.text(),
            project=self.project_name.text().strip(),
        )
        self.jobs_requested.emit(self.workspace_id.value, jobs)

    def set_presentation_state(self, state, message: str | None = None) -> None:
        super().set_presentation_state(state, message)
        state_name = state.value if hasattr(state, "value") else str(state)
        mouse_state = {
            "empty": "idle",
            "inputs_selected": "thinking",
            "preview": "thinking",
            "processing": "working",
            "success": "success",
            "error": "error",
        }.get(state_name, "idle")
        if hasattr(self, "mouse_mascot"):
            self.set_mouse_state(mouse_state)
