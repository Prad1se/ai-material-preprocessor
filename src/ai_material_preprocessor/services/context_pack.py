from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .document_provenance import ProvenanceKind, SourceSpan, extract_provenance
from .files import safe_component, unique_path
from .markdown_splitting import (
    estimate_tokens,
    split_oversized_markdown_block,
    structured_markdown_blocks,
)

CONTEXT_PACK_VERSION = 1
ESTIMATOR_NAME = "model-independent-heuristic"
ESTIMATOR_VERSION = 1
MIN_CUSTOM_BUDGET = 1_000
MAX_CUSTOM_BUDGET = 10_000_000
SOFT_TARGET_RATIO = 0.95
STABLE_FRAGMENT_TOKENS = 800


@dataclass(frozen=True)
class ContextBudget:
    requested_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.requested_tokens is None:
            return
        if isinstance(self.requested_tokens, bool) or not isinstance(self.requested_tokens, int):
            raise ValueError("Context Budget must be a positive integer.")
        if self.requested_tokens <= 0:
            raise ValueError("Context Budget must be a positive integer.")
        if self.requested_tokens < MIN_CUSTOM_BUDGET:
            raise ValueError(f"Context Budget must be at least {MIN_CUSTOM_BUDGET} tokens.")
        if self.requested_tokens > MAX_CUSTOM_BUDGET:
            raise ValueError(f"Context Budget must be at most {MAX_CUSTOM_BUDGET} tokens.")

    @property
    def soft_target_tokens(self) -> int | None:
        return (
            None
            if self.requested_tokens is None
            else int(self.requested_tokens * SOFT_TARGET_RATIO)
        )


@dataclass(frozen=True)
class PreparedContextSource:
    source_id: str
    source_order: int
    display_name: str
    source_format: str
    content: str
    provenance: tuple[SourceSpan, ...] = ()
    warnings: tuple[dict[str, object], ...] = ()
    processing_result: str = "success"
    sha256: str | None = None

    @property
    def estimated_tokens(self) -> int:
        return estimate_tokens(self.content)

    @property
    def provenance_level(self) -> str:
        kinds = {item.source_type.value for item in self.provenance}
        return ",".join(sorted(kinds)) if kinds else "document"


@dataclass(frozen=True)
class ContextBlock:
    block_id: str
    source_id: str
    source_order: int
    block_order: int
    heading_context: tuple[str, ...]
    content: str
    estimated_tokens: int
    provenance_refs: tuple[SourceSpan, ...]
    atomic: bool


@dataclass(frozen=True)
class ContextPackPart:
    index: int
    block_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    estimated_tokens: int
    over_budget: bool = False
    overflow_reason: str = ""


@dataclass(frozen=True)
class IntegrityReport:
    input_blocks: int
    packed_blocks: int
    missing_block_ids: tuple[str, ...]
    duplicate_block_ids: tuple[str, ...]
    order_preserved: bool

    @property
    def complete(self) -> bool:
        return not self.missing_block_ids and not self.duplicate_block_ids and self.order_preserved


@dataclass(frozen=True)
class ContextPackPlan:
    sources: tuple[PreparedContextSource, ...]
    blocks: tuple[ContextBlock, ...]
    packs: tuple[ContextPackPart, ...]
    budget: ContextBudget
    total_estimated_tokens: int
    warnings: tuple[dict[str, object], ...]
    integrity: IntegrityReport


@dataclass(frozen=True)
class ContextPackResult:
    output_dir: Path
    start_here: Path
    content: Path
    manifest: Path
    context_report: Path
    packs: tuple[Path, ...]
    plan: ContextPackPlan

    def quality_summary(self) -> dict[str, object]:
        return {
            "context_pack_version": CONTEXT_PACK_VERSION,
            "source_count": len(self.plan.sources),
            "requested_budget": self.plan.budget.requested_tokens,
            "soft_target": self.plan.budget.soft_target_tokens,
            "estimated_tokens": self.plan.total_estimated_tokens,
            "pack_count": len(self.plan.packs),
            "overflow_packs": sum(part.over_budget for part in self.plan.packs),
            "integrity": "complete" if self.plan.integrity.complete else "failed",
            "warnings": list(self.plan.warnings),
        }


class ContextSourceProcessor(Protocol):
    def __call__(self, source: Path, source_id: str, source_root: Path) -> Path: ...


def assign_source_ids(sources: tuple[Path, ...]) -> tuple[tuple[str, Path], ...]:
    return tuple((f"source-{index:03d}", path) for index, path in enumerate(sources, start=1))


def _provenance_for_block(
    provenance: tuple[SourceSpan, ...], start_line: int, end_line: int
) -> tuple[SourceSpan, ...]:
    return tuple(
        span for span in provenance if span.start_line <= end_line and span.end_line >= start_line
    )


def _context_blocks(sources: tuple[PreparedContextSource, ...]) -> tuple[ContextBlock, ...]:
    blocks: list[ContextBlock] = []
    for source in sorted(sources, key=lambda item: item.source_order):
        provenance = source.provenance or extract_provenance(
            source.content, source_suffix=source.source_format
        )
        block_order = 0
        for structured in structured_markdown_blocks(source.content):
            pieces = (
                (structured.content,)
                if structured.atomic
                else split_oversized_markdown_block(structured.content, STABLE_FRAGMENT_TOKENS)
            )
            for piece in pieces:
                block_order += 1
                blocks.append(
                    ContextBlock(
                        block_id=f"{source.source_id}-block-{block_order:04d}",
                        source_id=source.source_id,
                        source_order=source.source_order,
                        block_order=block_order,
                        heading_context=structured.heading_context,
                        content=piece,
                        estimated_tokens=estimate_tokens(piece),
                        provenance_refs=_provenance_for_block(
                            provenance, structured.start_line, structured.end_line
                        ),
                        atomic=structured.atomic,
                    )
                )
    return tuple(blocks)


def _block_metadata(block: ContextBlock) -> str:
    labels = ", ".join(dict.fromkeys(ref.label for ref in block.provenance_refs if ref.label))
    suffix = f" | provenance: {labels}" if labels else ""
    return f"<!-- block: {block.block_id} | source: {block.source_id}{suffix} -->"


def _rewrite_asset_links(content: str, source_id: str, *, from_packs: bool) -> str:
    if re.match(r"^\s*(`{3,}|~{3,})", content):
        return content
    asset_root = f"../sources/{source_id}/assets/" if from_packs else f"sources/{source_id}/assets/"
    parts = re.split(r"(`+[^`\n]*?`+)", content)
    pattern = re.compile(
        r"(?P<prefix>\]\(|\]:\s*|(?:src|href)=[\"'])(?:\./)?assets/",
        flags=re.IGNORECASE,
    )
    return "".join(
        part
        if index % 2
        else pattern.sub(lambda match: f"{match.group('prefix')}{asset_root}", part)
        for index, part in enumerate(parts)
    )


def _render_block(
    block: ContextBlock,
    source: PreparedContextSource,
    previous_source: str,
    *,
    from_packs: bool = False,
) -> str:
    parts: list[str] = []
    if block.source_id != previous_source:
        parts.append(f"## Source {source.source_id} — {source.display_name}")
    parts.extend(
        (
            _block_metadata(block),
            _rewrite_asset_links(block.content, block.source_id, from_packs=from_packs),
        )
    )
    return "\n\n".join(parts)


def _rendered_block_tokens(
    block: ContextBlock, source: PreparedContextSource, previous_source: str
) -> int:
    return estimate_tokens(_render_block(block, source, previous_source, from_packs=True))


def _pack_header(index: int, count: int, tokens: int, source_names: tuple[str, ...]) -> str:
    sources = "\n".join(f"- {name}" for name in source_names)
    return (
        f"# Context Pack {index} of {count}\n\n"
        f"Estimated tokens: ~{tokens}\n\n"
        "Sources included:\n"
        f"{sources}\n"
    )


def _estimated_pack_tokens(
    index: int,
    count: int,
    blocks: tuple[ContextBlock, ...],
    source_by_id: dict[str, PreparedContextSource],
) -> int:
    previous = ""
    body: list[str] = []
    for block in blocks:
        body.append(_render_block(block, source_by_id[block.source_id], previous, from_packs=True))
        previous = block.source_id
    source_ids = tuple(dict.fromkeys(block.source_id for block in blocks))
    source_names = tuple(source_by_id[source_id].display_name for source_id in source_ids)
    estimate = estimate_tokens("\n\n".join(body))
    for _attempt in range(3):
        rendered = _pack_header(index, count, estimate, source_names) + "\n" + "\n\n".join(body)
        updated = estimate_tokens(rendered)
        if updated == estimate:
            break
        estimate = updated
    return estimate


def _split_blocks(
    blocks: tuple[ContextBlock, ...],
    sources: tuple[PreparedContextSource, ...],
    budget: ContextBudget,
) -> list[list[ContextBlock]]:
    if budget.requested_tokens is None:
        return [list(blocks)]
    soft_target = budget.soft_target_tokens
    assert soft_target is not None
    source_by_id = {source.source_id: source for source in sources}
    groups: list[list[ContextBlock]] = []
    current: list[ContextBlock] = []
    current_tokens = 0
    previous_source = ""
    for block in blocks:
        source = source_by_id[block.source_id]
        block_tokens = _rendered_block_tokens(block, source, previous_source)
        if current and current_tokens + block_tokens > soft_target:
            groups.append(current)
            current = []
            current_tokens = 0
            previous_source = ""
            block_tokens = _rendered_block_tokens(block, source, previous_source)
        current.append(block)
        current_tokens += block_tokens
        previous_source = block.source_id
    if current or not groups:
        groups.append(current)
    return groups


def _integrity(
    blocks: tuple[ContextBlock, ...], packs: tuple[ContextPackPart, ...]
) -> IntegrityReport:
    expected = [block.block_id for block in blocks]
    actual = [block_id for pack in packs for block_id in pack.block_ids]
    seen: set[str] = set()
    duplicates: list[str] = []
    for block_id in actual:
        if block_id in seen and block_id not in duplicates:
            duplicates.append(block_id)
        seen.add(block_id)
    return IntegrityReport(
        input_blocks=len(expected),
        packed_blocks=len(actual),
        missing_block_ids=tuple(block_id for block_id in expected if block_id not in seen),
        duplicate_block_ids=tuple(duplicates),
        order_preserved=actual == expected,
    )


def build_context_plan(
    sources: tuple[PreparedContextSource, ...], budget: ContextBudget
) -> ContextPackPlan:
    if not sources:
        raise ValueError("At least one prepared source is required.")
    source_ids = [source.source_id for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Context source IDs must be unique.")
    blocks = _context_blocks(sources)
    source_by_id = {source.source_id: source for source in sources}
    groups = _split_blocks(blocks, sources, budget)
    parts: list[ContextPackPart] = []
    warnings: list[dict[str, object]] = [
        warning for source in sources for warning in source.warnings
    ]
    for index, group in enumerate(groups, start=1):
        group_blocks = tuple(group)
        estimated = _estimated_pack_tokens(index, len(groups), group_blocks, source_by_id)
        over_budget = bool(
            budget.requested_tokens is not None and estimated > budget.requested_tokens
        )
        atomic_overflow = over_budget and len(group_blocks) == 1 and group_blocks[0].atomic
        reason = (
            "A single atomic Markdown block cannot be safely split."
            if atomic_overflow
            else "Rendered pack exceeds the requested Context Budget."
            if over_budget
            else ""
        )
        if over_budget:
            warnings.append(
                {
                    "code": "context_pack_over_budget",
                    "pack": index,
                    "estimated_tokens": estimated,
                    "requested_budget": budget.requested_tokens,
                    "reason": reason,
                }
            )
        parts.append(
            ContextPackPart(
                index=index,
                block_ids=tuple(block.block_id for block in group_blocks),
                source_ids=tuple(dict.fromkeys(block.source_id for block in group_blocks)),
                estimated_tokens=estimated,
                over_budget=over_budget,
                overflow_reason=reason,
            )
        )
    packs = tuple(parts)
    integrity = _integrity(blocks, packs)
    if not integrity.complete:
        raise RuntimeError("Context Pack integrity validation failed.")
    return ContextPackPlan(
        sources=tuple(sorted(sources, key=lambda item: item.source_order)),
        blocks=blocks,
        packs=packs,
        budget=budget,
        total_estimated_tokens=sum(source.estimated_tokens for source in sources),
        warnings=tuple(warnings),
        integrity=integrity,
    )


def _integrity_dict(integrity: IntegrityReport) -> dict[str, object]:
    return {
        "input_blocks": integrity.input_blocks,
        "packed_blocks": integrity.packed_blocks,
        "missing_blocks": len(integrity.missing_block_ids),
        "missing_block_ids": list(integrity.missing_block_ids),
        "duplicate_blocks": len(integrity.duplicate_block_ids),
        "duplicate_block_ids": list(integrity.duplicate_block_ids),
        "order_preserved": integrity.order_preserved,
        "status": "complete" if integrity.complete else "failed",
    }


def _source_dict(source: PreparedContextSource) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "order": source.source_order,
        "display_name": source.display_name,
        "format": source.source_format,
        "estimated_tokens": source.estimated_tokens,
        "processing_result": source.processing_result,
        "provenance_level": source.provenance_level,
        "sha256": source.sha256,
        "warnings": list(source.warnings),
        "content": f"sources/{source.source_id}/content.md",
    }


def _block_dict(block: ContextBlock) -> dict[str, object]:
    return {
        "block_id": block.block_id,
        "source_id": block.source_id,
        "source_order": block.source_order,
        "block_order": block.block_order,
        "heading_context": list(block.heading_context),
        "estimated_tokens": block.estimated_tokens,
        "atomic": block.atomic,
        "content_sha256": hashlib.sha256(block.content.encode("utf-8")).hexdigest(),
        "provenance": [ref.to_dict() for ref in block.provenance_refs],
    }


def _pack_dict(part: ContextPackPart) -> dict[str, object]:
    return {
        "index": part.index,
        "file": f"packs/{part.index:03d}-context.md",
        "estimated_tokens": part.estimated_tokens,
        "source_ids": list(part.source_ids),
        "block_ids": list(part.block_ids),
        "status": "over_budget" if part.over_budget else "within_budget",
        "overflow_reason": part.overflow_reason or None,
    }


def _render_pack(
    part: ContextPackPart,
    plan: ContextPackPlan,
    block_by_id: dict[str, ContextBlock],
    source_by_id: dict[str, PreparedContextSource],
) -> str:
    blocks = tuple(block_by_id[block_id] for block_id in part.block_ids)
    source_names = tuple(source_by_id[source_id].display_name for source_id in part.source_ids)
    previous = ""
    body: list[str] = []
    for block in blocks:
        body.append(_render_block(block, source_by_id[block.source_id], previous, from_packs=True))
        previous = block.source_id
    header = _pack_header(part.index, len(plan.packs), part.estimated_tokens, source_names)
    status = f"\n> Warning: over budget. {part.overflow_reason}\n" if part.over_budget else ""
    return (header + status + "\n" + "\n\n".join(body)).rstrip() + "\n"


def write_context_pack(
    plan: ContextPackPlan,
    output_dir: Path,
    *,
    created_at: datetime | None = None,
) -> ContextPackResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    managed = (
        output_dir / "START_HERE.md",
        output_dir / "content.md",
        output_dir / "manifest.json",
        output_dir / "context-report.json",
    )
    if any(path.exists() for path in managed):
        raise FileExistsError(f"Context Pack output already exists: {output_dir}")
    packs_dir = output_dir / "packs"
    packs_dir.mkdir(exist_ok=False)
    block_by_id = {block.block_id: block for block in plan.blocks}
    source_by_id = {source.source_id: source for source in plan.sources}
    pack_paths: list[Path] = []
    for part in plan.packs:
        path = packs_dir / f"{part.index:03d}-context.md"
        path.write_text(_render_pack(part, plan, block_by_id, source_by_id), encoding="utf-8")
        pack_paths.append(path)

    content_parts = [
        "# Complete processed content",
        "",
        "> This archival file contains all processed source content and is not budget-limited.",
    ]
    previous = ""
    for block in plan.blocks:
        content_parts.extend(("", _render_block(block, source_by_id[block.source_id], previous)))
        previous = block.source_id
    content_path = output_dir / "content.md"
    content_path.write_text("\n".join(content_parts).rstrip() + "\n", encoding="utf-8")

    created = (created_at or datetime.now().astimezone()).isoformat(timespec="seconds")
    budget_dict = {
        "requested_tokens": plan.budget.requested_tokens,
        "soft_target_tokens": plan.budget.soft_target_tokens,
        "unit": "estimated_tokens",
    }
    sources = [_source_dict(source) for source in plan.sources]
    packs = [_pack_dict(part) for part in plan.packs]
    integrity = _integrity_dict(plan.integrity)
    manifest_payload = {
        "package_type": "ai_context_pack",
        "context_pack_version": CONTEXT_PACK_VERSION,
        "created_at": created,
        "main_markdown": "content.md",
        "start_here": "START_HERE.md",
        "context_report": "context-report.json",
        "estimator": {"name": ESTIMATOR_NAME, "version": ESTIMATOR_VERSION},
        "rendering": {"asset_links": "rebased_per_output_location"},
        "budget": budget_dict,
        "sources": sources,
        "packs": packs,
        "blocks": [_block_dict(block) for block in plan.blocks],
        "warnings": list(plan.warnings),
        "integrity": integrity,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_payload = {
        "context_pack_version": CONTEXT_PACK_VERSION,
        "created_at": created,
        "estimator": {"name": ESTIMATOR_NAME, "version": ESTIMATOR_VERSION},
        "budget": budget_dict,
        "total_estimated_tokens": plan.total_estimated_tokens,
        "pack_count": len(plan.packs),
        "source_count": len(plan.sources),
        "sources": sources,
        "packs": packs,
        "warnings": list(plan.warnings),
        "integrity": integrity,
    }
    report_path = output_dir / "context-report.json"
    report_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    budget_label = (
        "No limit"
        if plan.budget.requested_tokens is None
        else f"{plan.budget.requested_tokens:,} estimated tokens"
    )
    order = "\n".join(
        f"{part.index}. `packs/{part.index:03d}-context.md` — "
        f"~{part.estimated_tokens:,} estimated tokens"
        + (" — **over budget**" if part.over_budget else "")
        for part in plan.packs
    )
    inventory = "\n".join(
        f"- `{source.source_id}` — {source.display_name} "
        f"(~{source.estimated_tokens:,} estimated tokens)"
        for source in plan.sources
    )
    warning_lines = (
        "\n".join(
            f"- {warning.get('reason') or warning.get('message')}" for warning in plan.warnings
        )
        if plan.warnings
        else "- None"
    )
    start_here = output_dir / "START_HERE.md"
    start_here.write_text(
        "# AI Context Pack\n\n"
        f"Sources: {len(plan.sources)}\n\n"
        f"Estimated context: ~{plan.total_estimated_tokens:,} tokens\n\n"
        f"Context Budget: {budget_label}\n\n"
        f"Generated packs: {len(plan.packs)}\n\n"
        "## Suggested upload order\n\n"
        f"{order}\n\n"
        "Use the packs in their numbered deterministic order. `content.md` is the complete "
        "archive and is not constrained by the Context Budget.\n\n"
        "## Source inventory\n\n"
        f"{inventory}\n\n"
        "## Warnings\n\n"
        f"{warning_lines}\n\n"
        "## Provenance\n\n"
        "Each pack block carries a stable block ID, source ID, and the source labels that the "
        "existing document pipeline can reliably provide.\n\n"
        "No source content was intentionally removed.\n",
        encoding="utf-8",
    )
    return ContextPackResult(
        output_dir=output_dir,
        start_here=start_here,
        content=content_path,
        manifest=manifest_path,
        context_report=report_path,
        packs=tuple(pack_paths),
        plan=plan,
    )


def _source_span(payload: dict[str, object]) -> SourceSpan:
    raw_ordinal = payload.get("ordinal")
    raw_start = payload.get("start_line", 1)
    raw_end = payload.get("end_line", 1)
    raw_confidence = payload.get("confidence")
    return SourceSpan(
        source_type=ProvenanceKind(str(payload.get("source_type", "document"))),
        label=str(payload.get("label", "源文档")),
        ordinal=(
            int(raw_ordinal)
            if isinstance(raw_ordinal, int | str) and str(raw_ordinal).strip()
            else None
        ),
        start_line=int(raw_start) if isinstance(raw_start, int | str) else 1,
        end_line=int(raw_end) if isinstance(raw_end, int | str) else 1,
        confidence=(float(raw_confidence) if isinstance(raw_confidence, int | float) else None),
    )


def _load_prepared_source(
    source: Path, source_id: str, source_order: int, package_dir: Path
) -> PreparedContextSource:
    content_path = package_dir / "content.md"
    manifest_path = package_dir / "manifest.json"
    if not content_path.is_file() or not manifest_path.is_file():
        raise ValueError(f"Prepared source package is incomplete: {source_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"Prepared source manifest is invalid: {source_id}")
    raw_provenance = manifest.get("provenance", [])
    provenance = tuple(_source_span(item) for item in raw_provenance if isinstance(item, dict))
    raw_warnings = manifest.get("warnings", [])
    warnings = tuple(item for item in raw_warnings if isinstance(item, dict))
    source_metadata = manifest.get("source", {})
    metadata = source_metadata if isinstance(source_metadata, dict) else {}
    return PreparedContextSource(
        source_id=source_id,
        source_order=source_order,
        display_name=source.name,
        source_format=source.suffix.lower(),
        content=content_path.read_text(encoding="utf-8"),
        provenance=provenance,
        warnings=warnings,
        sha256=str(metadata.get("sha256")) if metadata.get("sha256") else None,
    )


_PRIVATE_PATH_PATTERN = re.compile(
    r"(?:file:/+(?:[A-Za-z]:)?[^\s<>'\"\]\)]+|"
    r"[A-Za-z]:[\\/][^\s<>'\"\]\)]+|"
    r"\\\\[^\s<>'\"\]\)]+|"
    r"/(?:Users|home|tmp|var/tmp)/[^\s<>'\"\]\)]+)",
    flags=re.IGNORECASE,
)


def _scrub_warning_paths(value: object) -> tuple[object, bool]:
    if isinstance(value, str):
        scrubbed, count = _PRIVATE_PATH_PATTERN.subn("[local path omitted]", value)
        return scrubbed, bool(count)
    if isinstance(value, list):
        changed = False
        list_values: list[object] = []
        for item in value:
            scrubbed_item, item_changed = _scrub_warning_paths(item)
            list_values.append(scrubbed_item)
            changed = changed or item_changed
        return list_values, changed
    if isinstance(value, dict):
        changed = False
        dict_values: dict[object, object] = {}
        for key, item in value.items():
            scrubbed_item, item_changed = _scrub_warning_paths(item)
            dict_values[key] = scrubbed_item
            changed = changed or item_changed
        return dict_values, changed
    return value, False


def _export_prepared_source(
    package_dir: Path, prepared: PreparedContextSource
) -> PreparedContextSource:
    private_paths = _PRIVATE_PATH_PATTERN.findall(prepared.content)
    if private_paths:
        raise ValueError(
            f"Processed content for {prepared.source_id} contains a local absolute path. "
            "Remove or convert that reference before creating a Context Pack."
        )
    scrubbed_warnings: list[dict[str, object]] = []
    redacted = False
    for warning in prepared.warnings:
        scrubbed, changed = _scrub_warning_paths(warning)
        if isinstance(scrubbed, dict):
            scrubbed_warnings.append(scrubbed)
        redacted = redacted or changed
    if redacted:
        scrubbed_warnings.append(
            {
                "code": "privacy_path_redacted",
                "message": "A local path was omitted from source diagnostics.",
            }
        )
    for item in tuple(package_dir.iterdir()):
        if item.name in {"content.md", "assets"}:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    exported = PreparedContextSource(
        source_id=prepared.source_id,
        source_order=prepared.source_order,
        display_name=prepared.display_name,
        source_format=prepared.source_format,
        content=prepared.content,
        provenance=prepared.provenance,
        warnings=tuple(scrubbed_warnings),
        processing_result=prepared.processing_result,
        sha256=prepared.sha256,
    )
    (package_dir / "source-manifest.json").write_text(
        json.dumps(_source_dict(exported), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return exported


def create_context_pack(
    *,
    sources: tuple[Path, ...],
    output_root: Path,
    budget: ContextBudget,
    source_processor: ContextSourceProcessor,
    on_progress=None,
    ensure_not_cancelled: Callable[[], None] | None = None,
) -> ContextPackResult:
    if not sources:
        raise ValueError("At least one source document is required.")
    output_root.mkdir(parents=True, exist_ok=True)
    first_name = safe_component(sources[0].stem, "Documents")
    suffix = f"-and-{len(sources) - 1}-more" if len(sources) > 1 else ""
    output_dir = unique_path(output_root / f"{first_name}{suffix}_AI-Context-Pack")
    output_dir.mkdir()
    source_root = output_dir / "sources"
    source_root.mkdir()
    prepared: list[PreparedContextSource] = []
    try:
        if ensure_not_cancelled:
            ensure_not_cancelled()
        total = len(sources)
        for order, (source_id, source) in enumerate(assign_source_ids(sources), start=1):
            if ensure_not_cancelled:
                ensure_not_cancelled()
            if on_progress:
                percent = 5 + round((order - 1) / total * 65)
                on_progress(percent, f"Converting source {order} of {total}: {source.name}")
            package_dir = source_processor(source, source_id, source_root)
            resolved_package = package_dir.resolve()
            if not resolved_package.is_relative_to(source_root.resolve()):
                raise ValueError("Prepared source package must stay inside the Context Pack.")
            loaded = _load_prepared_source(source, source_id, order, resolved_package)
            prepared.append(_export_prepared_source(resolved_package, loaded))
        if on_progress:
            on_progress(75, "Assembling source blocks")
        if ensure_not_cancelled:
            ensure_not_cancelled()
        plan = build_context_plan(tuple(prepared), budget)
        if on_progress:
            on_progress(88, "Writing Context Pack and integrity report")
        if ensure_not_cancelled:
            ensure_not_cancelled()
        result = write_context_pack(plan, output_dir)
        if on_progress:
            on_progress(94, "Context Pack ready")
        return result
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise
