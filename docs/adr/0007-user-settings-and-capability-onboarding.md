# ADR 0007: User settings and capability onboarding

## Status

Accepted for M5.

## Context

The application previously read `config.json` beside the executable and detected only raw tool
paths in the main window. An installed application may not be allowed to write beside its EXE, and
a permanent capability banner consumed space without helping the current workflow. First-time users
also needed a clear local-privacy explanation and actionable guidance for optional tools.

## Decision

- Store mutable user configuration under `%LOCALAPPDATA%\AI Material Preprocessor\config.json`.
- Deep-merge older configuration and migrate a legacy adjacent `config.json` without modifying it.
- Keep the main workbench focused on the selected files; show only feature-specific missing-tool
  guidance there.
- Put the complete capability table, versions, sources, installation hints, custom executable paths,
  and re-detection action in the first-run welcome dialog and graphical settings dialog.
- Represent tool health with typed available, missing, and version-warning states, while separately
  marking optional capabilities.
- Keep location resolution, OCR, and conversion local; capability detection never uploads files or
  coordinates.
- Provide explicit light, dark, and Windows-following themes with readable list, combo-box, disabled,
  selection, and focus states, and use Qt's pass-through high-DPI rounding policy.
- Expand a dropped folder recursively through a deterministic service that accepts only supported
  source extensions and de-duplicates resolved paths.

## Consequences

Settings remain writable for installed and portable builds, legacy users retain their preferences,
and first-run setup becomes self-explanatory. Version probing may briefly run local executables when
the welcome or settings dialog is opened; every probe uses the existing argument-array process runner
with a five-second timeout and no shell command composition.
