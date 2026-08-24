from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt

from ai_material_preprocessor.application.default_preview_registry import (
    build_default_preview_registry,
)
from ai_material_preprocessor.application.preview_registry import PreviewRequest
from ai_material_preprocessor.apps.video.preview import (
    VideoAIPackPreviewPlan,
)
from ai_material_preprocessor.models import Operation, ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.services.metadata import MediaMetadata
from ai_material_preprocessor.ui.workspaces.common import WorkspacePresentationState
from ai_material_preprocessor.ui.workspaces.video import VideoWorkspace


def _tools() -> dict[str, ToolStatus]:
    return {
        "ffmpeg": ToolStatus("ffmpeg", "ffmpeg.exe"),
        "ffprobe": ToolStatus("ffprobe", "ffprobe.exe"),
        "exiftool": ToolStatus("exiftool", None),
    }


def _workspace(qtbot) -> VideoWorkspace:
    workspace = VideoWorkspace(deepcopy(DEFAULT_CONFIG), _tools(), build_default_preview_registry())
    qtbot.addWidget(workspace)
    workspace.show()
    return workspace


def _select_pack(workspace: VideoWorkspace) -> None:
    index = workspace.operation.findData(Operation.VIDEO_AI_PACK.value)
    assert index >= 0
    workspace.operation.setCurrentIndex(index)


def test_video_ai_pack_mode_shows_only_pack_options_and_prepare_summary(
    qtbot, tmp_path: Path
) -> None:
    source = tmp_path / ("很长的中文课程录像名称" * 8 + ".mp4")
    source.touch()
    workspace = _workspace(qtbot)
    workspace.add_inputs([str(source)])
    _select_pack(workspace)

    assert workspace.include_audio.isVisibleTo(workspace)
    assert workspace.include_proxy.isVisibleTo(workspace)
    assert workspace.scene_sensitivity.isVisibleTo(workspace)
    assert workspace.max_keyframes.isVisibleTo(workspace)
    assert not workspace.quality.isVisibleTo(workspace)
    assert not workspace.audio_format.isVisibleTo(workspace)
    assert not workspace.location.isVisibleTo(workspace)
    assert workspace.start_button.text() == "创建视频 AI 资料包"
    assert "1 个视频" in workspace.output_hint.text()
    assert "音频：提取" in workspace.output_hint.text()
    assert "Proxy：不生成" in workspace.output_hint.text()
    assert workspace.file_list.item(0).toolTip() == str(source.resolve())
    assert workspace.include_audio.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_multi_source_pack_emits_one_job_with_current_options(qtbot, tmp_path: Path) -> None:
    sources = [tmp_path / "b.mp4", tmp_path / "a.mp4"]
    for source in sources:
        source.touch()
    workspace = _workspace(qtbot)
    workspace.add_inputs([str(source) for source in sources])
    _select_pack(workspace)
    workspace.include_audio.setChecked(False)
    workspace.include_proxy.setChecked(True)
    workspace.max_keyframes.setValue(12)
    emitted = []
    workspace.jobs_requested.connect(lambda name, jobs: emitted.append((name, jobs)))

    workspace._request_jobs()

    assert len(emitted) == 1
    jobs = emitted[0][1]
    assert len(jobs) == 1
    assert jobs[0].input_sources == tuple(workspace.paths)
    assert jobs[0].video_ai_pack_include_audio is False
    assert jobs[0].video_ai_pack_include_proxy is True
    assert jobs[0].video_ai_pack_max_keyframes == 12


def test_preview_plan_only_claims_pre_execution_facts(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "课程录像.mp4"
    source.write_bytes(b"video")
    metadata = MediaMetadata(
        captured_at=datetime.now().astimezone(),
        latitude=None,
        longitude=None,
        location_label="",
        source="ffprobe",
        duration_seconds=5.5,
        width=1280,
        height=720,
        codec="h264",
    )
    monkeypatch.setattr(
        "ai_material_preprocessor.apps.video.preview.read_media_metadata",
        lambda *_args, **_kwargs: metadata,
    )
    request = PreviewRequest(
        (source,),
        Operation.VIDEO_AI_PACK,
        tmp_path / "out",
        {"提取音频": "是", "生成 proxy": "否", "每个视频关键帧上限": 24},
        {},
    )

    plan = build_default_preview_registry().build(request)

    assert isinstance(plan, VideoAIPackPreviewPlan)
    assert plan.parameters["视频数量"] == "1"
    assert "5.500 秒" in plan.parameters["来源概览"]
    assert "1280x720" in plan.parameters["来源概览"]
    assert "实际关键帧数量" in plan.note
    assert "语义理解" in plan.note


def test_pack_processing_success_warning_error_and_timeline_action(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    pack = tmp_path / "Video-AI-Pack"
    pack.mkdir()
    (pack / "timeline.json").write_text("{}", encoding="utf-8")
    workspace = _workspace(qtbot)
    workspace.add_inputs([str(source)])
    _select_pack(workspace)
    workspace.set_progress(40, "正在提取关键帧")
    assert workspace.presentation_state is WorkspacePresentationState.PROCESSING
    assert workspace.mouse_mascot.property("state") == "working"

    report = {
        "video_ai_pack_version": 1,
        "source_count": 1,
        "frame_count": 3,
        "audio_count": 1,
        "proxy_count": 0,
        "warnings": [],
        "integrity": {"ok": True},
    }
    workspace.set_completed([str(pack)], [], [report])
    assert workspace.presentation_state is WorkspacePresentationState.SUCCESS
    assert workspace.mouse_mascot.property("state") == "success"
    assert "3 张关键帧" in workspace.state_label.text()
    assert workspace.timeline_button.isEnabled()
    opened = []
    workspace.open_output_requested.connect(opened.append)
    workspace.timeline_button.click()
    assert opened == [str(pack / "timeline.json")]

    workspace.set_completed(
        [str(pack)],
        [],
        [{**report, "warnings": [{"code": "audio_unavailable"}]}],
    )
    assert workspace.presentation_state is WorkspacePresentationState.WARNING
    assert workspace.mouse_mascot.property("state") == "thinking"

    workspace.set_completed([], ["failed"], [{**report, "integrity": {"ok": False}}])
    assert workspace.presentation_state is WorkspacePresentationState.ERROR
    assert workspace.mouse_mascot.property("state") == "error"


def test_pack_layout_remains_vertical_at_small_width(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    workspace = _workspace(qtbot)
    workspace.add_inputs([str(source)])
    _select_pack(workspace)
    workspace.resize(680, 600)
    qtbot.wait(20)

    assert workspace.content_layout.direction().name == "TopToBottom"
    assert workspace.output_hint.wordWrap()
