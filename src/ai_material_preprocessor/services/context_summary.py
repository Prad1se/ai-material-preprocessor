"""Context Pack summary derived from the pack's context-report.json.

The report file is the source of truth. This module never rescans packs,
markdown, or source directories.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class BudgetStatus(StrEnum):
    NO_LIMIT = "no_limit"
    WITHIN_BUDGET = "within_budget"
    OVER_BUDGET = "over_budget"


@dataclass(frozen=True)
class ContextPackSummary:
    source_count: int
    pack_count: int
    estimated_tokens: int
    requested_budget: int | None
    soft_target: int | None
    budget_status: BudgetStatus
    integrity_ok: bool
    overflow_count: int
    warnings: tuple[dict[str, object], ...]
    report_available: bool = True

    @property
    def overflow(self) -> bool:
        return self.overflow_count > 0

    @property
    def budget_label(self) -> str:
        if self.budget_status is BudgetStatus.NO_LIMIT or self.requested_budget is None:
            return "No limit"
        if self.requested_budget % 1000 == 0:
            return f"{self.requested_budget // 1000}K context window"
        return f"{self.requested_budget:,} estimated tokens"


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        parsed = int(value)
        return parsed if parsed >= 0 else None
    return None


def _coerce_budget(value: object) -> int | None:
    parsed = _coerce_int(value)
    return parsed if parsed is not None and parsed > 0 else None


def _budget_status(requested_budget: int | None, overflow_count: int) -> BudgetStatus:
    if requested_budget is None:
        return BudgetStatus.NO_LIMIT
    return BudgetStatus.OVER_BUDGET if overflow_count else BudgetStatus.WITHIN_BUDGET


def _empty_summary() -> ContextPackSummary:
    return ContextPackSummary(
        source_count=0,
        pack_count=0,
        estimated_tokens=0,
        requested_budget=None,
        soft_target=None,
        budget_status=BudgetStatus.NO_LIMIT,
        integrity_ok=False,
        overflow_count=0,
        warnings=(),
        report_available=False,
    )


def summarize_context_pack(pack_dir: Path) -> ContextPackSummary:
    report_path = pack_dir / "context-report.json"
    if not report_path.is_file():
        return _empty_summary()
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty_summary()
    if not isinstance(payload, dict):
        return _empty_summary()

    raw_budget = payload.get("budget")
    budget: dict[str, object] = raw_budget if isinstance(raw_budget, dict) else {}
    requested_budget = _coerce_budget(budget.get("requested_tokens"))
    soft_target = _coerce_budget(budget.get("soft_target_tokens"))

    integrity = payload.get("integrity")
    integrity_ok = isinstance(integrity, dict) and str(integrity.get("status")) == "complete"

    packs_value = payload.get("packs")
    pack_list = (
        [item for item in packs_value if isinstance(item, dict)]
        if isinstance(packs_value, list)
        else []
    )
    overflow_count = sum(1 for item in pack_list if str(item.get("status")) == "over_budget")

    warnings_value = payload.get("warnings")
    warnings = (
        tuple(item for item in warnings_value if isinstance(item, dict))
        if isinstance(warnings_value, list)
        else ()
    )

    return ContextPackSummary(
        source_count=_coerce_int(payload.get("source_count")) or 0,
        pack_count=_coerce_int(payload.get("pack_count")) or 0,
        estimated_tokens=_coerce_int(payload.get("total_estimated_tokens")) or 0,
        requested_budget=requested_budget,
        soft_target=soft_target,
        budget_status=_budget_status(requested_budget, overflow_count),
        integrity_ok=integrity_ok,
        overflow_count=overflow_count,
        warnings=warnings,
    )
