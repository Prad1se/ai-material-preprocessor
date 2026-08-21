from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from ..application.workspaces import WorkspaceId

WORKSPACE_LABELS = {
    WorkspaceId.DOCUMENTS: "Documents",
    WorkspaceId.VIDEO: "Video",
}


class CrossWorkspaceHandoffDialog(QDialog):
    """Ask before transferring foreign inputs; never starts processing."""

    def __init__(
        self,
        source: WorkspaceId,
        target: WorkspaceId,
        paths: list[Path],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("切换 Workspace？")
        layout = QVBoxLayout(self)
        target_label = WORKSPACE_LABELS[target]
        count = len(paths)
        message = QLabel(
            f"检测到 {count} 个属于 {target_label} Workspace 的文件。\n"
            f"是否切换到 {target_label} 并移交这些输入？"
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        note = QLabel("移交只会切换 Workspace 并加入输入列表，不会自动开始处理。")
        note.setObjectName("sectionDescription")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox()
        move = buttons.addButton(f"移交到 {target_label}", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        move.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        layout.addWidget(buttons)

    @classmethod
    def confirm(
        cls,
        source: WorkspaceId,
        target: WorkspaceId,
        paths: list[Path],
        parent: QWidget | None = None,
    ) -> bool:
        return cls(source, target, paths, parent).exec() == QDialog.DialogCode.Accepted
