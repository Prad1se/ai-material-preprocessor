from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage

from ai_material_preprocessor.application.default_preview_registry import (
    build_default_preview_registry,
)
from ai_material_preprocessor.models import Operation, ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.ui import document_mascot as document_mascot_module
from ai_material_preprocessor.ui.document_mascot import (
    DORO_STATE_ASSETS,
    DocumentMascotState,
    DocumentMascotView,
    transparentize_edge_background,
)
from ai_material_preprocessor.ui.settings_dialog import SettingsDialog
from ai_material_preprocessor.ui.theme import stylesheet_for_theme
from ai_material_preprocessor.ui.workspaces.common import WorkspacePresentationState
from ai_material_preprocessor.ui.workspaces.documents import DocumentWorkspace


def toolset(**available: bool) -> dict[str, ToolStatus]:
    return {
        name: ToolStatus(name, f"C:/tools/{name}.exe" if enabled else None)
        for name, enabled in {
            "markitdown": available.get("markitdown", False),
            "rapidocr": available.get("rapidocr", False),
            "libreoffice": available.get("libreoffice", False),
            "winword": available.get("winword", False),
            "powerpoint": available.get("powerpoint", False),
        }.items()
    }


def workspace(qtbot, **tools: bool) -> DocumentWorkspace:
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(**tools), build_default_preview_registry()
    )
    qtbot.addWidget(view)
    return view


def test_document_empty_state_prioritizes_input_over_options(qtbot) -> None:
    view = workspace(qtbot, markitdown=True)

    assert view.presentation_state is WorkspacePresentationState.EMPTY
    assert view.mascot_view.state is DocumentMascotState.EMPTY
    assert view.empty_guidance.isVisibleTo(view)
    assert not view.preparation_panel.isVisibleTo(view)
    assert view.start_button.text() == "准备文档"
    assert not view.start_button.isEnabled()
    assert "PDF" in view.input_description_label.text()


def test_document_mascot_declares_seven_bundled_asset_states() -> None:
    assert set(DORO_STATE_ASSETS) == set(DocumentMascotState)
    assert len({asset for asset in DORO_STATE_ASSETS.values() if asset}) == 7
    assert {
        DocumentMascotState.EMPTY,
        DocumentMascotState.READY,
        DocumentMascotState.PROCESSING,
        DocumentMascotState.SUCCESS,
        DocumentMascotState.WARNING,
        DocumentMascotState.ERROR,
        DocumentMascotState.COMPLETED,
    }.issubset(DocumentMascotState)
    assert DORO_STATE_ASSETS[DocumentMascotState.EMPTY] == "orange.png"
    assert DORO_STATE_ASSETS[DocumentMascotState.COMPLETED] == "resting.gif"
    assert DORO_STATE_ASSETS[DocumentMascotState.ERROR] is None


def test_bundled_doro_assets_use_supported_static_and_animated_formats() -> None:
    from PySide6.QtGui import QImageReader, QMovie

    root = Path(__file__).resolve().parents[1] / "assets" / "doro"
    filenames = {asset for asset in DORO_STATE_ASSETS.values() if asset}

    assert {Path(filename).suffix.casefold() for filename in filenames} == {
        ".gif",
        ".jpg",
        ".png",
        ".webp",
    }
    for filename in filenames:
        path = root / filename
        assert QImageReader(str(path)).canRead(), filename
        if path.suffix.casefold() == ".gif":
            assert QMovie(str(path)).isValid(), filename


def test_doro_edge_background_is_transparent_but_enclosed_white_is_preserved() -> None:
    from PySide6.QtGui import QColor

    image = QImage(9, 9, QImage.Format.Format_ARGB32)
    image.fill(QColor("#00ff00"))
    for x in range(2, 7):
        image.setPixelColor(x, 2, QColor("black"))
        image.setPixelColor(x, 6, QColor("black"))
    for y in range(2, 7):
        image.setPixelColor(2, y, QColor("black"))
        image.setPixelColor(6, y, QColor("black"))
    image.setPixelColor(4, 4, QColor("white"))

    rendered = transparentize_edge_background(image)

    assert rendered.pixelColor(0, 0).alpha() == 0
    assert rendered.pixelColor(4, 4).alpha() == 255
    assert rendered.pixelColor(2, 4).alpha() == 255


def test_document_mascot_loads_static_and_animated_local_overrides(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    from PySide6.QtGui import QColor

    static_image = QImage(24, 24, QImage.Format.Format_ARGB32)
    static_image.fill(QColor("white"))
    static_image.setPixelColor(12, 12, QColor("#f2a6c5"))
    assert static_image.save(str(tmp_path / "orange.png"))
    # A valid single-frame GIF is sufficient to exercise QMovie ownership/lifecycle.
    (tmp_path / "resting.gif").write_bytes(
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04"
        b"\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    )
    monkeypatch.setenv("AI_MATERIAL_DORO_ASSET_DIR", str(tmp_path))
    calls = 0
    original_transparentize = document_mascot_module.transparentize_edge_background

    def counted_transparentize(image):
        nonlocal calls
        calls += 1
        return original_transparentize(image)

    monkeypatch.setattr(
        document_mascot_module,
        "transparentize_edge_background",
        counted_transparentize,
    )
    mascot = DocumentMascotView()
    qtbot.addWidget(mascot)

    assert mascot.artwork.minimumSize() == mascot.artwork.maximumSize()
    assert mascot.artwork.width() == 140
    assert mascot.artwork.height() == 108

    mascot.set_state(DocumentMascotState.EMPTY)
    assert mascot.artwork.pixmap() is not None
    assert not mascot.artwork.pixmap().isNull()
    rendered = mascot.artwork.pixmap().toImage()
    assert rendered.pixelColor(0, 0).alpha() == 0
    assert rendered.pixelColor(rendered.width() // 2, rendered.height() // 2).alpha() > 0
    assert mascot.movie is None
    assert not mascot.symbol.isVisibleTo(mascot)

    mascot.set_state(DocumentMascotState.COMPLETED)
    assert mascot.movie is not None
    assert Path(mascot.movie.fileName()) == tmp_path / "resting.gif"
    assert mascot.artwork.movie() is None
    qtbot.waitUntil(lambda: mascot.artwork.pixmap() is not None)
    active_movie = mascot.movie
    qtbot.waitUntil(lambda: mascot.movie is not None and mascot.movie.currentFrameNumber() >= 0)
    frame = active_movie.currentFrameNumber()
    calls_after_first_render = calls
    mascot._render_movie_frame(frame)
    assert calls == calls_after_first_render
    mascot.set_state(DocumentMascotState.COMPLETED)
    assert mascot.movie is active_movie

    mascot.set_state(DocumentMascotState.EMPTY)
    assert active_movie.state().name == "NotRunning"
    assert mascot.movie is None
    assert mascot._movie_frame_cache == {}


def test_document_mascot_pauses_animation_while_workspace_is_hidden(qtbot, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("AI_MATERIAL_DORO_ASSET_DIR", str(root / "assets" / "doro"))
    mascot = DocumentMascotView()
    qtbot.addWidget(mascot)
    mascot.show()
    mascot.set_state(DocumentMascotState.PROCESSING)

    assert mascot.movie is not None
    qtbot.waitUntil(lambda: mascot.movie is not None and mascot.movie.state().name == "Running")
    mascot.hide()
    qtbot.waitUntil(lambda: mascot.movie is not None and mascot.movie.state().name == "Paused")
    mascot.show()
    qtbot.waitUntil(lambda: mascot.movie is not None and mascot.movie.state().name == "Running")


def test_document_mascot_keeps_accessible_fallback_when_asset_is_missing(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AI_MATERIAL_DORO_ASSET_DIR", str(tmp_path))
    mascot = DocumentMascotView()
    qtbot.addWidget(mascot)

    mascot.set_state(DocumentMascotState.WARNING)

    assert mascot.artwork.pixmap() is None or mascot.artwork.pixmap().isNull()
    assert not mascot.artwork.isVisibleTo(mascot)
    assert mascot.symbol.text() == "!"
    assert mascot.symbol.isVisibleTo(mascot)
    assert mascot.accessibleDescription() == "已完成，但有提醒"


def test_doro_assets_are_release_assets_with_separate_noncommercial_terms() -> None:
    root = Path(__file__).resolve().parents[1]
    filenames = {asset for asset in DORO_STATE_ASSETS.values() if asset}
    spec = (root / "app.spec").read_text(encoding="utf-8")
    asset_notice = (root / "assets" / "doro" / "README.md").read_text(encoding="utf-8")
    third_party_notices = (root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "assets/doro/local/" in (root / ".gitignore").read_text(encoding="utf-8")
    for filename in filenames:
        assert (root / "assets" / "doro" / filename).is_file()
        assert f'("assets/doro/{filename}", "assets/doro")' in spec
    assert "non-commercial" in asset_notice.casefold()
    assert "not licensed under the repository's mit license" in asset_notice.casefold()
    assert "doro" in third_party_notices.casefold()
    assert "non-commercial" in third_party_notices.casefold()


def test_document_input_is_rendered_as_compact_rows_with_type_size_and_path(
    qtbot, tmp_path: Path
) -> None:
    view = workspace(qtbot, markitdown=True)
    first = tmp_path / "很长的中文课程讲义第一章.pdf"
    second = tmp_path / "a-very-long-english-document-name-for-ai-preparation.txt"
    first.write_bytes(b"pdf")
    second.write_bytes(b"notes")

    view.add_inputs([str(first), str(second)])

    assert view.document_list.topLevelItemCount() == 2
    assert view.document_list.headerItem().text(0) == "文档"
    assert view.document_list.headerItem().text(1) == "类型"
    assert view.document_list.headerItem().text(2) == "大小"
    assert view.document_list.topLevelItem(0).toolTip(0)
    assert view.selected_count.text() == "已选择 2 个文档"
    assert view.preparation_panel.isVisibleTo(view)
    assert view.mascot_view.state is DocumentMascotState.READY


def test_document_processing_mode_uses_product_labels_without_changing_operation_data(
    qtbot, tmp_path: Path
) -> None:
    view = workspace(qtbot, markitdown=True)
    source = tmp_path / "lesson.docx"
    source.touch()
    view.add_inputs([str(source)])

    assert view.operation.currentData() == Operation.TO_MARKDOWN.value
    assert view.operation.currentText() == "AI 就绪 Markdown"
    assert "结构" in view.operation_description.text()
    assert view.start_button.text() == "准备文档"


def test_document_advanced_options_are_progressively_disclosed(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True, rapidocr=True)
    source = tmp_path / "lesson.docx"
    source.touch()
    view.add_inputs([str(source)])

    assert not view.advanced_panel.isVisibleTo(view)
    view.advanced_toggle.click()
    assert view.advanced_panel.isVisibleTo(view)
    assert view.target_tokens.isVisibleTo(view)
    view.advanced_toggle.click()
    assert not view.advanced_panel.isVisibleTo(view)


def test_missing_document_tool_is_explained_before_start(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot)
    source = tmp_path / "lesson.txt"
    source.touch()
    view.add_inputs([str(source)])

    assert view.operation.count() == 2
    assert view.operation.currentData() == Operation.TO_MARKDOWN.value
    assert not view.operation.model().item(0).isEnabled()
    assert not view.start_button.isEnabled()
    assert "MarkItDown" in view.tool_hint.text()
    assert view.setup_tool_button.isVisibleTo(view)


def test_context_pack_budget_is_only_visible_for_context_pack_mode(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True, rapidocr=True)
    sources = [tmp_path / "讲义一.txt", tmp_path / "lecture-two.txt"]
    for source in sources:
        source.write_text("notes", encoding="utf-8")
    view.add_inputs([str(source) for source in sources])

    assert not view.context_budget_panel.isVisibleTo(view)
    index = view.operation.findData(Operation.DOCUMENT_CONTEXT_PACK.value)
    view.operation.setCurrentIndex(index)

    assert view.context_budget_panel.isVisibleTo(view)
    assert view.context_budget.currentText() == "不限"
    assert not view.custom_budget.isVisibleTo(view)
    assert "预处理后可用" in str(view._parameters()["预计上下文"])

    view.context_budget.setCurrentIndex(view.context_budget.findData(64000))
    assert view._context_budget_value() == 64000
    view.context_budget.setCurrentIndex(view.context_budget.findData("custom"))
    view.custom_budget.setValue(1000)
    assert view.custom_budget.isVisibleTo(view)
    assert view._context_budget_value() == 1000


def test_context_pack_creates_one_multi_source_job_and_preserves_budget(
    qtbot, tmp_path: Path
) -> None:
    view = workspace(qtbot, markitdown=True)
    sources = [tmp_path / "one.txt", tmp_path / "two.txt"]
    for source in sources:
        source.write_text("notes", encoding="utf-8")
    view.add_inputs([str(source) for source in sources])
    view.operation.setCurrentIndex(view.operation.findData(Operation.DOCUMENT_CONTEXT_PACK.value))
    view.context_budget.setCurrentIndex(view.context_budget.findData(32000))
    emitted = []
    view.jobs_requested.connect(lambda workspace_id, jobs: emitted.append((workspace_id, jobs)))

    view._request_jobs()

    assert len(emitted) == 1
    jobs = emitted[0][1]
    assert len(jobs) == 1
    assert jobs[0].input_sources == tuple(sources)
    assert jobs[0].context_budget == 32000
    assert jobs[0].context_ocr_enabled is False
    assert view.config["document"]["context_pack_default_budget"] == 32000


def test_context_pack_completion_distinguishes_overflow_warning(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True)
    output = tmp_path / "pack"
    output.mkdir()
    report_file = {
        "context_pack_version": 1,
        "source_count": 3,
        "pack_count": 2,
        "total_estimated_tokens": 90000,
        "budget": {"requested_tokens": 32000, "soft_target_tokens": 30400},
        "packs": [
            {"index": 1, "status": "over_budget"},
            {"index": 2, "status": "within_budget"},
        ],
        "warnings": [
            {"code": "context_pack_over_budget", "reason": "Rendered pack exceeds the budget."}
        ],
        "integrity": {"status": "complete"},
    }
    (output / "context-report.json").write_text(
        json.dumps(report_file, ensure_ascii=False), encoding="utf-8"
    )

    view.set_completed([str(output)], [], [{"context_pack_version": 1}])

    assert view.presentation_state is WorkspacePresentationState.WARNING
    assert view.result_heading.text() == "AI 上下文包已准备好"
    assert "来源：3 个" in view.result_details.text()
    assert "上下文包：2 个" in view.result_details.text()
    assert "估算令牌：约 90,000 个" in view.result_details.text()
    assert "32K 上下文窗口" in view.result_details.text()
    assert "所有内容块均已保留" in view.result_details.text()
    assert "对应分包超出预算" in view.result_details.text()
    assert "超过预算" in view.state_message.text()
    assert view.report_button.isVisibleTo(view)
    assert view.source_map_button.isVisibleTo(view)


def test_context_pack_result_panel_renders_no_limit_summary(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True)
    output = tmp_path / "pack"
    output.mkdir()
    report_file = {
        "context_pack_version": 1,
        "source_count": 1,
        "pack_count": 1,
        "total_estimated_tokens": 751,
        "budget": {"requested_tokens": None, "soft_target_tokens": None},
        "packs": [{"index": 1, "status": "within_budget"}],
        "warnings": [],
        "integrity": {"status": "complete"},
    }
    (output / "context-report.json").write_text(
        json.dumps(report_file, ensure_ascii=False), encoding="utf-8"
    )

    view.set_completed([str(output)], [], [{"context_pack_version": 1}])

    assert view.presentation_state is WorkspacePresentationState.SUCCESS
    assert view.result_heading.text() == "AI 上下文包已准备好"
    assert "来源：1 个" in view.result_details.text()
    assert "上下文包：1 个" in view.result_details.text()
    assert "估算令牌：约 751 个" in view.result_details.text()
    assert "预算：不限" in view.result_details.text()
    assert "所有内容块均已保留" in view.result_details.text()
    assert "提醒：" not in view.result_details.text()
    assert view.source_map_button.isVisibleTo(view)


def test_context_pack_report_warning_uses_warning_presentation(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True)
    output = tmp_path / "pack"
    output.mkdir()
    (output / "context-report.json").write_text(
        json.dumps(
            {
                "context_pack_version": 1,
                "source_count": 1,
                "pack_count": 1,
                "total_estimated_tokens": 751,
                "budget": {"requested_tokens": None, "soft_target_tokens": None},
                "packs": [{"index": 1, "status": "within_budget"}],
                "warnings": [{"code": "source_warning", "reason": "Review this source."}],
                "integrity": {"status": "complete"},
            }
        ),
        encoding="utf-8",
    )

    view.set_completed([str(output)], [], [{"context_pack_version": 1}])

    assert view.presentation_state is WorkspacePresentationState.WARNING
    assert view.mascot_view.state is DocumentMascotState.WARNING
    assert "Review this source." in view.result_details.text()


def test_context_pack_missing_report_is_not_presented_as_ready(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True)
    output = tmp_path / "pack-without-report"
    output.mkdir()

    view.set_completed([str(output)], [], [{"context_pack_version": 1}])

    assert view.presentation_state is WorkspacePresentationState.WARNING
    assert view.result_heading.text() == "AI 上下文包需要检查"
    assert "context-report.json" in view.result_details.text()


def test_document_summary_and_mascot_follow_real_presentation_state(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True)
    source = tmp_path / "lesson.txt"
    source.touch()
    view.add_inputs([str(source)])

    assert "1 个文档" in view.summary_count.text()
    assert "AI 就绪 Markdown" in view.summary_mode.text()

    view.set_progress(40, "正在转换 lesson.txt")
    assert view.mascot_view.state is DocumentMascotState.PROCESSING
    assert "40%" in view.state_heading.text()

    view.set_presentation_state(WorkspacePresentationState.PREVIEW)
    assert view.mascot_view.state is DocumentMascotState.PREVIEW

    view.set_completed([str(tmp_path / "result.md")], ["one warning"])
    assert view.presentation_state is WorkspacePresentationState.WARNING
    assert view.mascot_view.state is DocumentMascotState.WARNING
    assert "1" in view.result_heading.text()
    assert view.result_details.isVisibleTo(view)

    view.set_presentation_state(WorkspacePresentationState.ERROR, "Conversion failed")
    assert view.mascot_view.state is DocumentMascotState.ERROR
    assert "Conversion failed" in view.state_message.text()
    assert view.technical_details_button.isVisibleTo(view)


def test_document_mascot_completes_after_finished_inputs_are_cleared(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True)
    source = tmp_path / "lesson.txt"
    source.touch()
    view.add_inputs([str(source)])
    view.set_completed([str(tmp_path / "result.md")], [])

    view.clear_inputs()

    assert view.presentation_state is WorkspacePresentationState.EMPTY
    assert view.mascot_view.state is DocumentMascotState.COMPLETED
    assert view.mascot_view.caption.text() == "Doro 正在休息"


def test_document_theme_has_explicit_light_and_dark_accessible_states() -> None:
    light = stylesheet_for_theme("light")
    dark = stylesheet_for_theme("dark")

    for selector in (
        "QFrame#documentDropPanel",
        "QFrame#documentSummary",
        "QFrame#documentStateWarning",
        "QWidget#documentMascot",
        "QPushButton#documentPrimary:focus",
        "QTreeWidget#documentList",
    ):
        assert selector in light
        assert selector in dark
    assert light != dark
    assert "#527463" in light
    assert "#8db59f" in dark


def test_document_selection_can_remove_only_selected_rows(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True)
    sources = [tmp_path / "one.txt", tmp_path / "two.txt"]
    for source in sources:
        source.touch()
    view.add_inputs([str(source) for source in sources])
    view.document_list.topLevelItem(0).setSelected(True)

    qtbot.mouseClick(view.remove_button, Qt.MouseButton.LeftButton)

    assert len(view.paths) == 1
    assert view.document_list.topLevelItemCount() == 1


def test_document_actions_remain_reachable_at_narrow_width(qtbot, tmp_path: Path) -> None:
    view = workspace(qtbot, markitdown=True)
    view.resize(760, 900)
    view.show()
    source = tmp_path / "lesson.txt"
    source.write_text("notes", encoding="utf-8")
    view.add_inputs([str(source)])
    view.set_completed([str(tmp_path / "result.md")], [], [])

    scroll = view.content_stack.widget(0)
    assert scroll.horizontalScrollBar().maximum() == 0
    visible_actions = (
        view.add_button,
        view.folder_button,
        view.remove_button,
        view.reveal_button,
        view.clear_button,
        view.preview_button,
        view.start_button,
        view.open_button,
    )
    for widget in visible_actions:
        if not widget.isVisibleTo(view):
            continue
        top_left = widget.mapTo(view, QPoint(0, 0))
        bottom_right = widget.mapTo(view, widget.rect().bottomRight())
        assert top_left.x() >= 0
        assert bottom_right.x() <= view.width()


def test_documents_settings_open_on_processing_defaults_and_document_tools(qtbot) -> None:
    dialog = SettingsDialog(
        deepcopy(DEFAULT_CONFIG),
        toolset(),
        save_callback=lambda _: None,
        detector=lambda _: toolset(),
        initial_tab="documents",
    )
    qtbot.addWidget(dialog)

    assert dialog.settings_tabs.currentIndex() == 1
    assert dialog.settings_tabs.tabText(1) == "文档"
    assert dialog.document_mode.currentData() in {"enhanced", "raw"}
