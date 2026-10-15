from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget


class AppSystemTray(QObject):
    """Small, optional tray surface that does not change close-window behavior."""

    def __init__(self, app: QApplication, window: QWidget, icon: QIcon) -> None:
        super().__init__(app)
        self.app = app
        self.window = window
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("AI 素材预处理工具")

        self.menu = QMenu()
        self.open_action = QAction("打开 AI 素材预处理工具", self.menu)
        self.quit_action = QAction("退出", self.menu)
        self.menu.addAction(self.open_action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)
        self.tray_icon.setContextMenu(self.menu)

        self.open_action.triggered.connect(self.show_window)
        self.quit_action.triggered.connect(self.app.quit)
        self.tray_icon.activated.connect(self._activated)

    def show(self) -> bool:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        self.tray_icon.show()
        return True

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.show_window()
