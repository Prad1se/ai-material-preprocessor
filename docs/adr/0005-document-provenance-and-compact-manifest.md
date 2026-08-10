# ADR 0005: Document provenance and compact AI package manifest

## Status

Accepted for the 2.0 Release Candidate.

## Context

AI-readable Markdown loses visual layout and may combine text extracted from multiple pages,
slides, worksheets, or OCR observations. A quality warning or chunk is only actionable when it can
be traced back to its source. The previous manifest duplicated the full quality report, target
settings, absolute private paths, and a verbose file inventory even though the application already
stores detailed history centrally.

## Decision

- Parse stable markers emitted by MarkItDown and the local OCR pipeline into typed source spans.
- Use document-level provenance when the source format does not expose reliable page boundaries.
- Add source labels and Markdown line numbers to actionable quality issues.
- Split Markdown structurally, keeping fenced code, tables, block formulas, and heading/content
  pairs intact whenever they fit under the hard limit.
- Keep the full quality report in memory and centralized history only.
- Write a compact format-version-2 package manifest with the source name and SHA-256, format,
  creation time, mode, tool versions, main Markdown file, ordered chunks, assets, provenance, OCR
  confidence metadata, and warning summaries.
- Never write the source's absolute path or extracted document body into the package manifest.

## Consequences

Packages are smaller, safer to share, and easier for automation to consume. Source mapping is exact
when markers exist and document-level otherwise; Word page numbers cannot be reconstructed reliably
without a layout renderer, so the manifest must not invent them. Existing format-version-1 package
manifests remain readable as plain JSON but new packages use version 2.
