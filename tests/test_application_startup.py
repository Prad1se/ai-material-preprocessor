from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from ai_material_preprocessor.__main__ import configure_high_dpi


def test_high_dpi_uses_pass_through_rounding_policy(monkeypatch) -> None:
    policies = []
    monkeypatch.setattr(
        QGuiApplication,
        "setHighDpiScaleFactorRoundingPolicy",
        lambda policy: policies.append(policy),
    )

    configure_high_dpi()

    assert policies == [Qt.HighDpiScaleFactorRoundingPolicy.PassThrough]
