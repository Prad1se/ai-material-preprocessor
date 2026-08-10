# ADR 0002: Incremental service boundaries and quality gates

Status: accepted
Date: 2026-08-10

## Context

The 1.4 application proved its workflows, but the GUI worker dispatched every conversion directly,
external commands could block forever, errors could expose raw tool output, and document
post-processing lived in one large module. The 2.0 plan requires persistent tasks, cancellation,
previews, provenance, and a reproducible release pipeline.

## Decision

1. Keep Python and PySide6. Introduce boundaries incrementally instead of rewriting the app.
2. Treat Qt workers as presentation adapters. Operation dispatch belongs to `JobExecutor`, with
   separate document and video application services.
3. Represent lifecycle and error categories with `StrEnum` and dataclasses. Public messages are
   separated from technical diagnostics so dialogs do not disclose private paths by default.
4. Route external commands through `ProcessRunner`, always with an argument sequence,
   `shell=False`, a timeout, and a cancellation token. Existing converter APIs remain compatible.
5. Split Markdown cleaning, quality checking, and structural splitting into separate modules while
   retaining compatibility exports from `document_enhancement`.
6. Use Ruff 0.16.x for formatting/linting and mypy 2.x for gradual static checking. Both are
   development-only MIT-licensed tools and do not enter the packaged runtime.

## Consequences

- M1 can persist and schedule jobs without importing GUI classes.
- Running-process cancellation is available at the infrastructure boundary; M1 must propagate the
  cancellation token through services and converters.
- Technical details can be stored in protected history details while ordinary dialogs stay safe.
- Formatting touches existing Python files once, producing a larger M0 diff but a stable automated
  style gate for later milestones.
- The large window construction remains a known hotspot. M5 will split pages/components when the
  navigation and settings information architecture is implemented.

## Sources

- Ruff formatter: https://docs.astral.sh/ruff/formatter/
- Ruff linter: https://docs.astral.sh/ruff/linter/
- Ruff license: https://github.com/astral-sh/ruff/blob/main/LICENSE
- mypy documentation: https://mypy.readthedocs.io/en/stable/getting_started.html
- mypy license: https://github.com/python/mypy/blob/master/LICENSE
