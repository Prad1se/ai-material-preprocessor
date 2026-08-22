from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtWidgets import QTabWidget

from ai_material_preprocessor.application.workspaces import (
    WorkspaceId,
    workspace_for_operation,
)
from ai_material_preprocessor.gui import MainWindow
from ai_material_preprocessor.models import Operation, ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.services.history_repository import HistoryRepository
from ai_material_preprocessor.services.task_manifest import TaskRecord, write_task_manifest
from ai_material_preprocessor.ui.history_dialog import HistoryDialog
from ai_material_preprocessor.ui.settings_dialog import SettingsDialog
from ai_material_preprocessor.ui.workspaces.common import WorkspacePresentationState


def toolset(**available: bool) -> dict[str, ToolStatus]:
    names = (
        "markitdown",
        "ffmpeg",
        "ffprobe",
        "exiftool",
        "libreoffice",
        "winword",
        "powerpoint",
        "rapidocr",
    )
    return {
        name: ToolStatus(name, f"C:/tools/{name}.exe" if available.get(name, False) else None)
        for name in names
    }


def operations(combo) -> list[Operation]:
    return [Operation(combo.itemData(index)) for index in range(combo.count())]


def test_shell_defaults_to_documents_and_restores_last_workspace(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    saved: list[dict] = []
    window = MainWindow(config=config, tools=toolset(), config_saver=saved.append)
    qtbot.addWidget(window)

    assert window.current_workspace is WorkspaceId.DOCUMENTS
    window.switch_workspace(WorkspaceId.VIDEO)
    assert window.current_workspace is WorkspaceId.VIDEO
    assert saved[-1]["ui"]["last_workspace"] == WorkspaceId.VIDEO.value

    restored = MainWindow(config=saved[-1], tools=toolset(), config_saver=lambda _: None)
    qtbot.addWidget(restored)
    assert restored.current_workspace is WorkspaceId.VIDEO


def test_switching_workspace_keeps_both_workspace_state_and_active_worker(
    qtbot, tmp_path: Path
) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=toolset(markitdown=True, ffmpeg=True),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)
    document = tmp_path / "lesson.docx"
    video = tmp_path / "clip.mp4"
    document.touch()
    video.touch()
    window.document_workspace.add_inputs([str(document)])
    window.video_workspace.add_inputs([str(video)])
    window.document_workspace.operation.setCurrentIndex(
        window.document_workspace.operation.findData(Operation.DOCUMENT_CONTEXT_PACK.value)
    )
    window.document_workspace.context_budget.setCurrentIndex(
        window.document_workspace.context_budget.findData(64000)
    )
    marker = object()
    window.worker = marker  # type: ignore[assignment]

    window.switch_workspace(WorkspaceId.VIDEO)
    window.switch_workspace(WorkspaceId.DOCUMENTS)

    assert window.worker is marker
    assert window.document_workspace.paths == [document.resolve()]
    assert (
        window.document_workspace.operation.currentData() == Operation.DOCUMENT_CONTEXT_PACK.value
    )
    assert window.document_workspace._context_budget_value() == 64000
    assert window.video_workspace.paths == [video.resolve()]


def test_document_and_video_workspaces_only_expose_their_operations(qtbot, tmp_path: Path) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=toolset(markitdown=True, winword=True, ffmpeg=True),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)
    document = tmp_path / "lesson.docx"
    video = tmp_path / "clip.mp4"
    document.touch()
    video.touch()

    window.document_workspace.add_inputs([str(document)])
    window.video_workspace.add_inputs([str(video)])

    document_operations = operations(window.document_workspace.operation)
    video_operations = operations(window.video_workspace.operation)
    assert document_operations == [
        Operation.TO_MARKDOWN,
        Operation.DOCUMENT_CONTEXT_PACK,
        Operation.TO_PDF,
    ]
    assert set(document_operations).isdisjoint(
        {Operation.COMPRESS_VIDEO, Operation.EXTRACT_AUDIO, Operation.STANDARDIZE_MP4}
    )
    assert video_operations == [
        Operation.COMPRESS_VIDEO,
        Operation.EXTRACT_AUDIO,
        Operation.STANDARDIZE_MP4,
        Operation.KEYFRAMES_CONTACT_SHEET,
        Operation.RENAME_VIDEO,
        Operation.ORGANIZE_VIDEO,
    ]
    assert Operation.TO_MARKDOWN not in video_operations


def test_wrong_workspace_handoff_moves_input_without_starting_job(qtbot, tmp_path: Path) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=toolset(markitdown=True, ffmpeg=True),
        config_saver=lambda _: None,
        handoff_confirmer=lambda _source, _target, _paths: True,
    )
    qtbot.addWidget(window)
    video = tmp_path / "clip.mp4"
    video.touch()

    window.document_workspace.add_inputs([str(video)])

    assert window.current_workspace is WorkspaceId.VIDEO
    assert window.video_workspace.paths == [video.resolve()]
    assert window.document_workspace.paths == []
    assert window.worker is None


def test_wrong_workspace_handoff_cancel_keeps_both_inputs_empty(qtbot, tmp_path: Path) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=toolset(markitdown=True, ffmpeg=True),
        config_saver=lambda _: None,
        handoff_confirmer=lambda _source, _target, _paths: False,
    )
    qtbot.addWidget(window)
    document = tmp_path / "lesson.docx"
    document.touch()

    window.switch_workspace(WorkspaceId.VIDEO)
    window.video_workspace.add_inputs([str(document)])

    assert window.current_workspace is WorkspaceId.VIDEO
    assert window.video_workspace.paths == []
    assert window.document_workspace.paths == []
    assert window.worker is None


def test_workspace_is_derived_from_operation_without_persistence_changes() -> None:
    assert workspace_for_operation(Operation.TO_MARKDOWN) is WorkspaceId.DOCUMENTS
    assert workspace_for_operation(Operation.TO_PDF) is WorkspaceId.DOCUMENTS
    assert workspace_for_operation(Operation.COMPRESS_VIDEO) is WorkspaceId.VIDEO


def test_history_dialog_filters_by_derived_workspace(qtbot, tmp_path: Path) -> None:
    history = tmp_path / "History"
    document = tmp_path / "lesson.docx"
    video = tmp_path / "clip.mp4"
    document.touch()
    video.touch()
    write_task_manifest(
        history,
        [TaskRecord(document, Operation.TO_MARKDOWN, "success")],
        created_at=datetime(2026, 8, 21, tzinfo=UTC),
        task_id="document-task",
    )
    write_task_manifest(
        history,
        [TaskRecord(video, Operation.COMPRESS_VIDEO, "success")],
        created_at=datetime(2026, 8, 21, 1, tzinfo=UTC),
        task_id="video-task",
    )

    dialog = HistoryDialog(HistoryRepository(history), workspace=WorkspaceId.DOCUMENTS)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "lesson.docx"
    dialog.workspace_filter.setCurrentIndex(
        dialog.workspace_filter.findData(WorkspaceId.VIDEO.value)
    )
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "clip.mp4"


def test_document_history_surfaces_existing_quality_summary(qtbot, tmp_path: Path) -> None:
    history = tmp_path / "History"
    document = tmp_path / "lesson.docx"
    document.touch()
    write_task_manifest(
        history,
        [
            TaskRecord(
                document,
                Operation.TO_MARKDOWN,
                "success",
                quality_summary={
                    "score": 88,
                    "estimated_tokens": 2400,
                    "chunk_count": 3,
                },
            )
        ],
        created_at=datetime(2026, 8, 21, tzinfo=UTC),
        task_id="quality-document-task",
    )

    dialog = HistoryDialog(HistoryRepository(history), workspace=WorkspaceId.DOCUMENTS)
    qtbot.addWidget(dialog)

    assert dialog.table.horizontalHeaderItem(5).text() == "质量摘要"
    assert dialog.table.item(0, 5).text() == "88/100 · 约 2,400 个估算令牌 · 3 段"


def test_settings_are_partitioned_into_general_documents_and_video(qtbot) -> None:
    dialog = SettingsDialog(
        deepcopy(DEFAULT_CONFIG),
        toolset(),
        save_callback=lambda _: None,
        detector=lambda _: toolset(),
    )
    qtbot.addWidget(dialog)

    tabs = dialog.findChild(QTabWidget, "settingsTabs")
    assert tabs is not None
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "常规",
        "文档",
        "视频",
    ]
    assert set(dialog.document_tool_paths).isdisjoint(dialog.video_tool_paths)


def test_old_config_without_workspace_state_opens_documents_without_schema_bump(qtbot) -> None:
    config = deepcopy(DEFAULT_CONFIG)
    config.pop("ui")
    schema_version = config["app"]["schema_version"]

    window = MainWindow(config=config, tools=toolset(), config_saver=lambda _: None)
    qtbot.addWidget(window)

    assert window.current_workspace is WorkspaceId.DOCUMENTS
    assert window.config["app"]["schema_version"] == schema_version


def test_each_workspace_creates_only_its_own_jobs(qtbot, tmp_path: Path) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=toolset(markitdown=True, ffmpeg=True),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)
    document = tmp_path / "lesson.txt"
    video = tmp_path / "clip.mp4"
    document.touch()
    video.touch()
    requested: list[tuple[str, list]] = []

    for workspace, source in (
        (window.document_workspace, document),
        (window.video_workspace, video),
    ):
        workspace.jobs_requested.disconnect()
        workspace.jobs_requested.connect(
            lambda raw_workspace, jobs: requested.append((raw_workspace, jobs))
        )
        workspace.add_inputs([str(source)])
        workspace.start_button.click()

    assert requested[0][0] == WorkspaceId.DOCUMENTS.value
    assert requested[0][1][0].operation is Operation.TO_MARKDOWN
    assert requested[1][0] == WorkspaceId.VIDEO.value
    assert requested[1][1][0].operation is Operation.COMPRESS_VIDEO


def test_workspace_presentation_states_are_independent(qtbot) -> None:
    window = MainWindow(
        config=deepcopy(DEFAULT_CONFIG),
        tools=toolset(),
        config_saver=lambda _: None,
    )
    qtbot.addWidget(window)

    window.document_workspace.set_presentation_state(WorkspacePresentationState.PREVIEW)
    window.video_workspace.set_presentation_state(WorkspacePresentationState.ERROR)

    assert window.document_workspace.presentation_state is WorkspacePresentationState.PREVIEW
    assert window.video_workspace.presentation_state is WorkspacePresentationState.ERROR
    assert window.video_workspace.mouse_mascot.property("state") == "error"
