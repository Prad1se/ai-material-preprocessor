from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_material_preprocessor.services.context_summary import (
    BudgetStatus,
    summarize_context_pack,
)


def _write_report(pack_dir: Path, payload: dict[str, object]) -> None:
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "context-report.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_summary_parses_complete_report(tmp_path: Path) -> None:
    _write_report(
        tmp_path / "pack",
        {
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
                {"code": "context_pack_over_budget", "reason": "Over the requested budget."}
            ],
            "integrity": {
                "input_blocks": 4,
                "packed_blocks": 4,
                "missing_blocks": 0,
                "duplicate_blocks": 0,
                "order_preserved": True,
                "status": "complete",
            },
        },
    )

    summary = summarize_context_pack(tmp_path / "pack")

    assert summary.source_count == 3
    assert summary.pack_count == 2
    assert summary.estimated_tokens == 90000
    assert summary.requested_budget == 32000
    assert summary.soft_target == 30400
    assert summary.budget_status is BudgetStatus.OVER_BUDGET
    assert summary.overflow_count == 1
    assert summary.integrity_ok is True
    assert len(summary.warnings) == 1
    assert summary.warnings[0]["code"] == "context_pack_over_budget"


def test_summary_missing_report_falls_back_to_empty(tmp_path: Path) -> None:
    summary = summarize_context_pack(tmp_path / "missing")

    assert summary.source_count == 0
    assert summary.pack_count == 0
    assert summary.estimated_tokens == 0
    assert summary.requested_budget is None
    assert summary.integrity_ok is False
    assert summary.warnings == ()


def test_summary_malformed_report_falls_back_to_empty(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "context-report.json").write_text("{not json", encoding="utf-8")

    summary = summarize_context_pack(pack_dir)

    assert summary.source_count == 0
    assert summary.integrity_ok is False


def test_summary_missing_fields_fall_back_to_defaults(tmp_path: Path) -> None:
    _write_report(tmp_path / "pack", {"context_pack_version": 1})

    summary = summarize_context_pack(tmp_path / "pack")

    assert summary.source_count == 0
    assert summary.pack_count == 0
    assert summary.estimated_tokens == 0
    assert summary.requested_budget is None
    assert summary.soft_target is None
    assert summary.budget_status is BudgetStatus.NO_LIMIT
    assert summary.integrity_ok is False
    assert summary.warnings == ()


def test_summary_reports_failed_integrity(tmp_path: Path) -> None:
    _write_report(
        tmp_path / "pack",
        {
            "integrity": {
                "missing_blocks": 1,
                "duplicate_blocks": 0,
                "order_preserved": True,
                "status": "failed",
            }
        },
    )

    assert summarize_context_pack(tmp_path / "pack").integrity_ok is False


def test_summary_budget_status_no_limit_without_requested_budget(tmp_path: Path) -> None:
    _write_report(tmp_path / "pack", {"budget": {"requested_tokens": None}})

    summary = summarize_context_pack(tmp_path / "pack")

    assert summary.requested_budget is None
    assert summary.budget_status is BudgetStatus.NO_LIMIT
    assert summary.overflow_count == 0


def test_summary_budget_status_within_budget_when_no_overflow(tmp_path: Path) -> None:
    _write_report(
        tmp_path / "pack",
        {
            "budget": {"requested_tokens": 64000},
            "packs": [{"index": 1, "status": "within_budget"}],
        },
    )

    summary = summarize_context_pack(tmp_path / "pack")

    assert summary.requested_budget == 64000
    assert summary.budget_status is BudgetStatus.WITHIN_BUDGET
    assert summary.overflow_count == 0


def test_summary_ignores_malformed_pack_and_warning_entries(tmp_path: Path) -> None:
    _write_report(
        tmp_path / "pack",
        {
            "packs": ["not-a-dict", {"index": 2, "status": "over_budget"}],
            "warnings": ["not-a-dict", {"code": "real_warning"}],
        },
    )

    summary = summarize_context_pack(tmp_path / "pack")

    assert summary.overflow_count == 1
    assert len(summary.warnings) == 1
    assert summary.warnings[0]["code"] == "real_warning"


@pytest.mark.parametrize("value", ["5", 5])
def test_summary_coerces_string_integers(tmp_path: Path, value: object) -> None:
    _write_report(tmp_path / "pack", {"source_count": value, "pack_count": 2})

    summary = summarize_context_pack(tmp_path / "pack")

    assert summary.source_count == 5
    assert summary.pack_count == 2


def test_summary_falsy_counts_default_to_zero(tmp_path: Path) -> None:
    _write_report(tmp_path / "pack", {"source_count": 0, "pack_count": "0"})

    summary = summarize_context_pack(tmp_path / "pack")

    assert summary.source_count == 0
    assert summary.pack_count == 0
