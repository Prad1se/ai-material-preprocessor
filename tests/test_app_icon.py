from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon, QImage

from ai_material_preprocessor.ui import system_tray
from ai_material_preprocessor.ui.app_icon import app_icon_path, load_app_icon
from ai_material_preprocessor.ui.system_tray import AppSystemTray


class FakeSystemTrayIcon(QObject):
    """Avoid native Shell/COM ownership in an ordinary Qt unit test."""

    activated = Signal(object)

    def __init__(self, _icon: QIcon, parent=None) -> None:
        super().__init__(parent)
        self._tooltip = ""
        self.menu = None

    def setToolTip(self, value: str) -> None:
        self._tooltip = value

    def toolTip(self) -> str:
        return self._tooltip

    def setContextMenu(self, menu) -> None:
        self.menu = menu


class FakeWindow(QObject):
    """Keep action-wiring coverage outside the native Windows window manager."""

    def __init__(self) -> None:
        super().__init__()
        self.visible = False
        self.raised = False
        self.activated = False

    def show(self) -> None:
        self.visible = True

    def raise_(self) -> None:
        self.raised = True

    def activateWindow(self) -> None:
        self.activated = True


def test_application_icon_is_multisize_and_loadable(qtbot) -> None:
    path = app_icon_path()
    icon = load_app_icon()

    assert path.is_file()
    assert path.suffix == ".ico"
    assert not icon.isNull()
    for size in (16, 32, 48, 256):
        image = icon.pixmap(size, size).toImage()
        assert not image.isNull()
        assert image.hasAlphaChannel()


def test_icon_is_used_by_packaging_and_installer() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = (root / "app.spec").read_text(encoding="utf-8")
    installer = (root / "installer" / "ai-material-preprocessor.nsi").read_text(encoding="utf-8")

    assert '("assets/app-icon.ico", "assets")' in spec
    assert 'icon="assets/app-icon.ico"' in spec
    assert 'MUI_ICON "${PROJECT_ROOT}\\assets\\app-icon.ico"' in installer
    assert 'MUI_UNICON "${PROJECT_ROOT}\\assets\\app-icon.ico"' in installer


def test_system_tray_has_accessible_actions_without_changing_close_behavior(
    qapp, monkeypatch
) -> None:
    app = qapp
    monkeypatch.setattr(system_tray, "QSystemTrayIcon", FakeSystemTrayIcon)
    window = FakeWindow()
    tray = AppSystemTray(app, window, QIcon(str(app_icon_path())))

    assert tray.tray_icon.toolTip() == "AI 素材预处理工具"
    assert tray.open_action.text() == "打开 AI 素材预处理工具"
    assert tray.quit_action.text() == "退出"
    assert app.quitOnLastWindowClosed()

    tray.open_action.trigger()
    assert window.visible
    assert window.raised
    assert window.activated


def test_icon_master_has_real_transparency() -> None:
    root = Path(__file__).resolve().parents[1]
    image = QImage(str(root / "assets" / "app-icon.png"))

    assert not image.isNull()
    assert image.hasAlphaChannel()
    assert image.pixelColor(0, 0).alpha() == 0
