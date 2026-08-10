from pathlib import Path

from ai_material_preprocessor.services.startup_maintenance import perform_startup_maintenance


class FakeHistoryRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def cleanup(self, *, retention_days: int, max_bytes: int):
        self.calls.append((retention_days, max_bytes))


def test_startup_maintenance_applies_configured_retention_and_capacity(tmp_path: Path) -> None:
    repository = FakeHistoryRepository()

    perform_startup_maintenance(
        {
            "history": {"retention_days": 45, "max_size_mb": 256},
            "history_directory": str(tmp_path / "History"),
        },
        history_repository=repository,
    )

    assert repository.calls == [(45, 256 * 1024 * 1024)]


def test_startup_maintenance_uses_safe_defaults_for_invalid_manual_config() -> None:
    repository = FakeHistoryRepository()

    perform_startup_maintenance(
        {"history": {"retention_days": "invalid", "max_size_mb": None}},
        history_repository=repository,
    )

    assert repository.calls == [(90, 512 * 1024 * 1024)]
