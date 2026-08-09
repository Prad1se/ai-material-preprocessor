# 2.0 engineering baseline

Date: 2026-08-10
Stable baseline: `main` at `1443400`
Milestone branch: `agent/architecture-baseline`

## Verified baseline

- Source test suite: 80 passed, 1 optional Office test skipped.
- Existing packaged EXE self-test: passed for MarkItDown, RapidOCR, FFmpeg, ffprobe, and
  storyboard generation.
- Detected on the development machine: Microsoft Word and PowerPoint.
- Not detected on the development machine: LibreOffice and ExifTool.
- The existing packaged artifact is useful as a behavioral baseline, but it is not accepted as a
  reproducible 2.0 build. M6 will rebuild and verify all release artifacts from a clean checkout.

## Architecture before M0

- `gui.py` combined widget construction, styling, background execution, operation dispatch,
  history writing, and completion reporting in roughly 845 lines.
- `document_enhancement.py` combined cleaning, quality checks, splitting, OCR post-processing,
  and package persistence in roughly 461 lines.
- `converters/common.py` used one blocking `subprocess.run` call without timeout or cancellation.
- Task status was represented by ad-hoc strings and a batch existed only for the lifetime of one
  GUI worker thread.
- CI ran pytest only; it did not enforce formatting, linting, typing, packaging, or checksums.

## M0 boundary introduced

```text
Qt MainWindow
  -> Qt Worker adapter
    -> JobExecutor
      -> DocumentConversionService -> converters -> mature document tools
      -> VideoProcessingService    -> converters -> FFmpeg / metadata tools

External tools -> ProcessRunner -> typed UserFacingError

AI document package
  -> markdown_cleaning
  -> markdown_quality
  -> markdown_splitting
  -> document_enhancement orchestration
```

The boundaries are deliberately incremental. Existing converter functions remain available and
their behavior remains covered by regression tests; the project is not being rewritten.

## Gap matrix after baseline audit

| Milestone | Already present | Required gap |
|---|---|---|
| M0 | Basic typed jobs, converter modules, 80 tests | Persistent status enum, safe errors, process adapter, thin worker, split document modules, public fixture catalog, lint/type gates |
| M1 | One sequential in-memory batch, central task manifests, clear-all history | Persistent queue, per-item progress, cancel/retry/recovery, disk estimate, search/filter, selected deletion, retention/quota, cache separation |
| M2 | Rename preview and completion quality dialog | Document pre/post preview, outline/OCR/risk localization, media facts, contact-sheet preview, size/risk estimates, history detail |
| M3 | Cleaning, OCR appendix, chunks, package manifest | Slim manifest v2, source hash/tool versions, page/slide/sheet provenance, localized issues, stronger table/code/formula-safe splitting |
| M4 | Basic metadata fallback, naming preview, video transforms, storyboard | Full metadata view, capture-time rules, local place dictionary, project/device fields, organization, duplicate detection, timestamped contact sheets |
| M5 | One mouse-themed window and runtime detection | First-run guide, settings pages, custom paths, re-detection, folder drop, contextual install help, light/dark themes and DPI QA |
| M6 | PyInstaller onedir ZIP script and pytest CI | Installer, reproducible build, version gate, build CI, SHA verification, packaged smoke test, release docs/templates, consented update check, clean-Windows proof |

## Dependency decisions

- Keep MarkItDown, Microsoft Office/LibreOffice, FFmpeg/ffprobe, ExifTool, RapidOCR, ONNX
  Runtime, and pypdfium2 as the mature domain engines. The application owns orchestration and
  user experience, not parsing, rendering, codecs, OCR inference, or media metadata decoding.
- Add Ruff for deterministic formatting/import ordering/linting. Ruff is active, MIT licensed,
  and provides both a linter and formatter.
- Add mypy as a gradual static type checker. Mypy is active, supports incremental adoption, and is
  MIT licensed.

No new runtime dependency was added in M0.
