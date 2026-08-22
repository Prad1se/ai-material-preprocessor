from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from ai_material_preprocessor.application.default_preview_registry import (
    build_default_preview_registry,
)
from ai_material_preprocessor.models import ToolStatus
from ai_material_preprocessor.services.config import DEFAULT_CONFIG
from ai_material_preprocessor.services.context_pack import ContextBudget, create_context_pack
from ai_material_preprocessor.services.document_provenance import ProvenanceKind, SourceSpan
from ai_material_preprocessor.services.source_map import load_source_map
from ai_material_preprocessor.services.source_open import (
    SourceOpenCapability,
    SourceOpenTarget,
)
from ai_material_preprocessor.ui.source_map_view import DEGRADED_CONTENT, SourceMapView
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


def _build_pack(tmp_path: Path, sources: list[tuple[str, str, tuple[SourceSpan, ...]]]):
    contents = {
        f"source-{index:03d}": content
        for index, (_name, content, _spans) in enumerate(sources, start=1)
    }
    spans = {
        f"source-{index:03d}": value
        for index, (_name, _content, value) in enumerate(sources, start=1)
    }
    inputs: list[Path] = []
    for index, (name, _content, _spans) in enumerate(sources, start=1):
        source = tmp_path / "inputs" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"original-{index}", encoding="utf-8")
        inputs.append(source)

    def processor(source: Path, source_id: str, source_root: Path) -> Path:
        package = source_root / source_id
        package.mkdir(parents=True)
        (package / "raw.md").write_text("raw", encoding="utf-8")
        (package / "content.md").write_text(contents[source_id], encoding="utf-8")
        (package / "manifest.json").write_text(
            json.dumps(
                {
                    "source": {"name": source.name, "format": source.suffix, "sha256": "a" * 64},
                    "provenance": [span.to_dict() for span in spans[source_id]],
                    "warnings": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return package

    return create_context_pack(
        sources=tuple(inputs),
        output_root=tmp_path / "outputs",
        budget=ContextBudget(None),
        source_processor=processor,
    )


def _pdf_page() -> tuple[str, str, tuple[SourceSpan, ...]]:
    return (
        "lecture.pdf",
        "<!-- Page: 37 -->\n\nPDF paragraph.",
        (SourceSpan(ProvenanceKind.PAGE, "第 37 页", 37, 1, 3),),
    )


def _context_report() -> dict[str, object]:
    return {
        "context_pack_version": 1,
        "source_count": 1,
        "pack_count": 1,
        "estimated_tokens": 50,
        "requested_budget": None,
        "overflow_packs": 0,
    }


def test_source_map_view_empty_state(qtbot) -> None:
    view = SourceMapView()
    qtbot.addWidget(view)

    assert view._stack.currentWidget() is view._empty_page
    assert view.empty_label.isVisibleTo(view)
    assert view.empty_label.text() == "No Source Map available"
    assert view.blocks_table.rowCount() == 0


def test_source_map_view_loads_entries_and_renders_source_card(qtbot, tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    view = SourceMapView()
    qtbot.addWidget(view)

    view.set_source_map(load_source_map(result.output_dir))

    assert view._stack.currentWidget() is view._body_page
    assert view.blocks_table.rowCount() == len(load_source_map(result.output_dir).entries)
    assert "blocks" in view.block_count.text()
    assert view.card_file_value.text() == "lecture.pdf"
    assert view.card_format_value.text() == ".pdf"
    assert view.card_source_id_value.text() == "source-001"
    assert view.card_location_value.text() == "PDF page 37"
    assert not view.card_fallback_note.isVisibleTo(view)
    assert view.content_edit.toPlainText()


def test_source_map_view_renders_document_level_fallback(qtbot, tmp_path: Path) -> None:
    result = _build_pack(
        tmp_path,
        [
            (
                "notes.docx",
                "Notes.",
                (SourceSpan(ProvenanceKind.DOCUMENT, "Word 文档", None, 1, 1),),
            )
        ],
    )
    view = SourceMapView()
    qtbot.addWidget(view)

    view.set_source_map(load_source_map(result.output_dir))

    assert view.card_location_value.text() == "Document-level fallback"
    assert view.card_fallback_note.isVisibleTo(view)


def test_source_map_view_shows_open_capability_and_emits_runtime_target(
    qtbot, tmp_path: Path
) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    source_path = tmp_path / "inputs" / "lecture.pdf"
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    manifest["sources"][0]["sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    result.manifest.write_text(json.dumps(manifest), encoding="utf-8")
    source_map = load_source_map(result.output_dir)
    view = SourceMapView()
    qtbot.addWidget(view)
    emitted: list[SourceOpenTarget] = []
    view.open_source_requested.connect(emitted.append)

    view.set_source_map(source_map, {"source-001": source_path})

    assert view.card_capability_value.text() == "Page-level (viewer permitting)"
    assert view.open_source_button.isEnabled()
    view.open_source_button.click()
    assert emitted[0].capability is SourceOpenCapability.PAGE_LEVEL
    assert emitted[0].path == source_path
    assert emitted[0].page == 37


def test_source_map_view_disables_open_when_runtime_path_is_missing(qtbot, tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    view = SourceMapView()
    qtbot.addWidget(view)

    view.set_source_map(load_source_map(result.output_dir))

    assert view.card_capability_value.text() == "Unavailable"
    assert not view.open_source_button.isEnabled()
    assert "unavailable" in view.open_source_note.text().casefold()


def test_source_map_view_selection_syncs_content_and_source_card(qtbot, tmp_path: Path) -> None:
    result = _build_pack(
        tmp_path,
        [
            ("a.pdf", "Alpha.", (SourceSpan(ProvenanceKind.PAGE, "第 1 页", 1, 1, 1),)),
            ("b.pdf", "Beta.", (SourceSpan(ProvenanceKind.PAGE, "第 2 页", 2, 1, 1),)),
        ],
    )
    source_map = load_source_map(result.output_dir)
    view = SourceMapView()
    qtbot.addWidget(view)
    view.set_source_map(source_map)

    assert view.blocks_table.rowCount() == 2
    view.blocks_table.setCurrentCell(1, 0)
    qtbot.waitUntil(lambda: view.content_edit.toPlainText() == "Beta.")

    assert view.content_edit.toPlainText() == "Beta."
    assert view.card_file_value.text() == "b.pdf"
    assert view.card_source_id_value.text() == "source-002"
    assert view.card_location_value.text() == "PDF page 2"


def test_source_map_view_shows_degraded_content_without_fake_data(qtbot, tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    manifest_path = result.output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for block in manifest["blocks"]:
        block["content_sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    view = SourceMapView()
    qtbot.addWidget(view)

    view.set_source_map(load_source_map(result.output_dir))

    assert view.content_edit.toPlainText() == DEGRADED_CONTENT
    assert view.card_location_value.text() == "PDF page 37"
    assert view.integrity_notice.isVisibleTo(view)


def test_document_workspace_opens_source_map_page_from_context_pack_result(
    qtbot, tmp_path: Path
) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(markitdown=True), build_default_preview_registry()
    )
    qtbot.addWidget(view)

    view.set_completed([str(result.output_dir)], [], [_context_report()])

    assert view.source_map_button.isVisibleTo(view)
    view.source_map_button.click()
    assert view.content_stack.currentWidget() is view.source_map_view
    assert view.source_map_view.blocks_table.rowCount() >= 1
    assert view.source_map_view.card_location_value.text() == "PDF page 37"


def test_document_workspace_keeps_verified_source_open_target_after_inputs_clear(
    qtbot, tmp_path: Path
) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    source_path = tmp_path / "inputs" / "lecture.pdf"
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    manifest["sources"][0]["sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    result.manifest.write_text(json.dumps(manifest), encoding="utf-8")
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(markitdown=True), build_default_preview_registry()
    )
    qtbot.addWidget(view)
    view.add_inputs([str(source_path)])
    view.operation.setCurrentIndex(view.operation.findData("document_context_pack"))
    view._request_jobs()
    view.set_completed([str(result.output_dir)], [], [_context_report()])
    view.clear_inputs()

    view.source_map_button.click()

    assert view.source_map_view.card_capability_value.text() == "Page-level (viewer permitting)"
    assert view.source_map_view.open_source_button.isEnabled()


def test_document_workspace_back_button_returns_to_flow(qtbot, tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(markitdown=True), build_default_preview_registry()
    )
    qtbot.addWidget(view)
    view.set_completed([str(result.output_dir)], [], [_context_report()])

    view.source_map_button.click()
    assert view.content_stack.currentIndex() == 1
    view.source_map_view.back_button.click()
    assert view.content_stack.currentIndex() == 0


def test_document_workspace_hides_source_map_button_without_context_pack(
    qtbot, tmp_path: Path
) -> None:
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(markitdown=True), build_default_preview_registry()
    )
    qtbot.addWidget(view)

    view.set_completed([str(tmp_path / "result.md")], [], [])

    assert not view.source_map_button.isVisibleTo(view)
    assert view._source_map_pack_dir is None


def test_document_workspace_copy_for_ai_copies_pack_text(qtbot, tmp_path: Path) -> None:
    from ai_material_preprocessor.services.context_copy import build_context_copy

    result = _build_pack(tmp_path, [_pdf_page()])
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(markitdown=True), build_default_preview_registry()
    )
    qtbot.addWidget(view)
    view.set_completed([str(result.output_dir)], [], [_context_report()])

    assert view.copy_for_ai_button.isVisibleTo(view)
    view.copy_for_ai_button.click()

    assert QApplication.clipboard().text() == build_context_copy(result.output_dir)
    assert view.copy_for_ai_button.text() == "Copied ✓"


def test_document_workspace_copy_for_ai_hidden_without_context_pack(qtbot, tmp_path: Path) -> None:
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(markitdown=True), build_default_preview_registry()
    )
    qtbot.addWidget(view)

    view.set_completed([str(tmp_path / "result.md")], [], [])

    assert not view.copy_for_ai_button.isVisibleTo(view)


def test_document_workspace_clears_stale_source_map_for_next_result(qtbot, tmp_path: Path) -> None:
    result = _build_pack(tmp_path, [_pdf_page()])
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(markitdown=True), build_default_preview_registry()
    )
    qtbot.addWidget(view)
    view.set_completed([str(result.output_dir)], [], [_context_report()])
    view.source_map_button.click()
    assert view.source_map_view.blocks_table.rowCount() >= 1

    view.set_completed([str(tmp_path / "result.md")], [], [])

    assert view.content_stack.currentIndex() == 0
    assert view.source_map_view.blocks_table.rowCount() == 0
    assert view.source_map_view.content_edit.toPlainText() == ""
    assert not view.source_map_button.isVisibleTo(view)
    assert view._source_map_pack_dir is None


def test_document_workspace_context_pack_experience_actions_integration(
    qtbot, tmp_path: Path
) -> None:
    from ai_material_preprocessor.services.context_copy import build_context_copy

    result = _build_pack(tmp_path, [_pdf_page()])
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(markitdown=True), build_default_preview_registry()
    )
    qtbot.addWidget(view)
    view.set_completed([str(result.output_dir)], [], [_context_report()])

    assert view.result_heading.text() == "AI Context Pack Ready"
    assert view.copy_for_ai_button.isVisibleTo(view)
    assert view.source_map_button.isVisibleTo(view)
    assert view.open_button.isEnabled()

    view.source_map_button.click()
    assert view.content_stack.currentWidget() is view.source_map_view
    assert view.source_map_view.blocks_table.rowCount() >= 1
    view.source_map_view.back_button.click()
    assert view.content_stack.currentIndex() == 0

    view.copy_for_ai_button.click()
    assert QApplication.clipboard().text() == build_context_copy(result.output_dir)
    assert view.copy_for_ai_button.text() == "Copied ✓"

    view.set_completed([str(tmp_path / "result.md")], [], [])
    assert not view.copy_for_ai_button.isVisibleTo(view)
    assert not view.source_map_button.isVisibleTo(view)
    assert view.source_map_view.blocks_table.rowCount() == 0


def test_document_workspace_opens_pdf_page_then_falls_back_to_document(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(markitdown=True), build_default_preview_registry()
    )
    qtbot.addWidget(view)
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"pdf")
    target = SourceOpenTarget(
        source_id="source-001",
        path=path,
        capability=SourceOpenCapability.PAGE_LEVEL,
        page=37,
        reason="Page-level location (viewer permitting).",
    )
    opened = []

    def open_url(url):
        opened.append(url)
        return len(opened) == 2

    monkeypatch.setattr(QDesktopServices, "openUrl", open_url)

    view._open_source_target(target)

    assert len(opened) == 2
    assert opened[0].fragment() == "page=37"
    assert opened[1].fragment() == ""
    assert Path(opened[1].toLocalFile()) == path


def test_document_workspace_document_level_open_does_not_fake_fragment(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    view = DocumentWorkspace(
        deepcopy(DEFAULT_CONFIG), toolset(markitdown=True), build_default_preview_registry()
    )
    qtbot.addWidget(view)
    path = tmp_path / "notes.docx"
    path.write_bytes(b"docx")
    target = SourceOpenTarget(
        source_id="source-001",
        path=path,
        capability=SourceOpenCapability.DOCUMENT_LEVEL,
        page=None,
        reason="Document-level location.",
    )
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)

    view._open_source_target(target)

    assert len(opened) == 1
    assert opened[0].fragment() == ""
    assert Path(opened[0].toLocalFile()) == path
