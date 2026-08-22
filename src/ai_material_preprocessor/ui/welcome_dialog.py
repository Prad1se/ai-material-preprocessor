from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .theme import stylesheet_for_theme


class WelcomeDialog(QDialog):
    import_documents = Signal()
    view_example = Signal()
    continue_setup = Signal()

    def __init__(
        self,
        *,
        examples_dir: Path | None = None,
        theme: str = "system",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._examples_dir = examples_dir
        self.setWindowTitle("欢迎")
        self.setModal(False)
        self.resize(720, 400)
        self.setMinimumSize(600, 360)
        self._build_ui()
        self.setStyleSheet(stylesheet_for_theme(theme))

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 30)
        root.setSpacing(16)

        hero = QHBoxLayout()
        copy = QVBoxLayout()
        eyebrow = QLabel("AI 素材预处理工具  ·  本地优先")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("欢迎使用")
        title.setObjectName("title")
        subtitle = QLabel(
            "为 AI 准备文档——将 PDF、Office 文件和笔记整理为清晰、可追踪的 AI 上下文包。"
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(subtitle)
        hero.addLayout(copy, 1)
        root.addLayout(hero)

        steps = QLabel("导入文档 → 生成 AI 上下文包 → 复制给 AI → 追踪来源")
        steps.setObjectName("sectionDescription")
        steps.setWordWrap(True)
        root.addWidget(steps)

        privacy = QLabel("本地优先：文件保留在本机，且永远不会覆盖原文件。")
        privacy.setObjectName("outputHint")
        privacy.setWordWrap(True)
        root.addWidget(privacy)

        root.addStretch()

        actions = QHBoxLayout()
        self.setup_button = QPushButton("继续设置")
        self.setup_button.setObjectName("linkButton")
        self.example_button = QPushButton("查看示例")
        self.example_button.setObjectName("secondary")
        self.example_button.setVisible(self._examples_dir is not None)
        self.import_button = QPushButton("导入文档")
        self.import_button.setObjectName("primary")
        actions.addWidget(self.setup_button)
        actions.addStretch()
        actions.addWidget(self.example_button)
        actions.addWidget(self.import_button)
        root.addLayout(actions)

        self.import_button.clicked.connect(self._import_clicked)
        self.example_button.clicked.connect(self._example_clicked)
        self.setup_button.clicked.connect(self._setup_clicked)

    def _import_clicked(self) -> None:
        self.accept()
        self.import_documents.emit()

    def _example_clicked(self) -> None:
        self.accept()
        self.view_example.emit()

    def _setup_clicked(self) -> None:
        self.accept()
        self.continue_setup.emit()
