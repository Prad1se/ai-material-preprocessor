from ai_material_preprocessor.models import TaskStatus


def test_task_status_has_all_persistent_lifecycle_states() -> None:
    assert {status.value for status in TaskStatus} == {
        "waiting",
        "running",
        "success",
        "failed",
        "cancelled",
        "interrupted",
    }


def test_only_terminal_task_states_are_finished() -> None:
    assert TaskStatus.WAITING.is_terminal is False
    assert TaskStatus.RUNNING.is_terminal is False
    assert TaskStatus.SUCCESS.is_terminal is True
    assert TaskStatus.FAILED.is_terminal is True
    assert TaskStatus.CANCELLED.is_terminal is True
    assert TaskStatus.INTERRUPTED.is_terminal is True
