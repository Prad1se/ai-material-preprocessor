> [English](README.md) | [中文](README.md)

# AI Material Preprocessor

> Turn documents and videos into clean, AI-ready materials — locally on your Windows PC.

[![Tests](https://github.com/Prad1se/ai-material-preprocessor/actions/workflows/tests.yml/badge.svg)](https://github.com/Prad1se/ai-material-preprocessor/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/Prad1se/ai-material-preprocessor)](https://github.com/Prad1se/ai-material-preprocessor/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A local Windows desktop app that turns raw documents (PDF, Word, PowerPoint, Excel, HTML, and more) and video files into structured, AI-friendly materials. It is not just a format converter: it **converts, cleans, structures, traces sources, and produces AI-ready output**.

- Documents → clean Markdown packages with cleaning, quality checks, structural splitting, source tracing, and optional local OCR
- Video → standardized, named, deduplicated creative assets with keyframe contact sheets
- Local-first: processing happens on your machine, and source files are never overwritten

**Status**: public stable release **2.0.0rc1**. Newer capabilities (such as one-click supplementation of missing tools from Settings) are already merged into `main` and will ship in the next release.

<!-- TODO: hero image at assets/gallery/hero.png — Before (messy raw files) → After (a clean AI-ready package) -->

## Why

Dropping raw files directly into an AI often goes wrong:

- A PDF is a layout, not text: scanned pages have no text layer, so the AI cannot "read" them.
- Repeated headers, footers, and PowerPoint template text pollute the context.
- Long documents exceed the context window, and the AI loses track.
- Tables, code blocks, and formulas get mangled or lost during conversion.
- Sources cannot be traced, so there is no way to verify where a claim came from.

Converting alone is not enough. An AI needs **clean, well-structured, chunked text with traceable sources**. This project handles the preprocessing step before AI consumption — it does not replace the AI itself.

## Demo / Use Cases

### Course materials

<!-- TODO: GIF at assets/gallery/demo-course.gif -->

- **Input**: a set of PDF / PPTX course decks
- **Process**: convert to Markdown → remove repeated headers, footers, and template text → fix heading structure → quality check → structural chunking → (optional) local OCR
- **Output**: an AI study package (`content.md` + `chunks/` + `assets/` + `manifest.json`), where each chunk is tagged with its source page or slide
- **Value**: hand an entire course to an AI for Q&A, summarization, or review — with clean and traceable content

### Research materials

<!-- TODO: screenshot at assets/gallery/demo-paper.png -->

- **Input**: PDF papers
- **Process**: convert → quality checks (table integrity, formula/image risks) → source mapping
- **Output**: Markdown with localized risk warnings, per-chunk source labels, and a slim manifest (source hash, tool versions)
- **Value**: build a verifiable research library where the AI's claims can be traced back to specific pages

### Video assets

<!-- TODO: GIF at assets/gallery/demo-video.gif -->

- **Input**: raw video files with inconsistent names and formats
- **Process**: read metadata → name by time/location → deduplicate → compress or standardize → extract keyframes
- **Output**: an organized library (by year/date/location) plus a keyframe contact-sheet overview
- **Value**: hundreds of clips become a browsable, searchable, reusable library in minutes — originals untouched

## Features

### Make documents easier for AI to read

- One-click conversion to Markdown: PDF, DOCX, PPTX, XLSX, HTML, CSV, JSON, XML, TXT, EPUB
- Automatic cleaning: removes repeated headers, footers, and PowerPoint template text; fixes skipped heading levels; unifies code fences and inline/block formula markers
- Structure preservation: adds clear separators for slides and worksheet headings, keeping tables, fenced code, and block formulas intact

### Preserve structure and source information

- Structure-aware splitting: splits by headings and target length (about 4000 tokens per segment by default, adjustable); `chunks/` is generated only when content actually exceeds one segment
- Source tracing: every chunk and every warning maps to a line number and its source page, slide, worksheet, or OCR page
- Quality checks: table corruption, possible formula loss, missing images, skipped heading levels, and more
- Slim manifest: records source hash, tool versions, provenance, chunk order, and warning summaries — no absolute paths, document bodies, or full reports
- Optional local OCR: reads images, PDF pages, and images embedded in Office files; off by default; added as supplementary text, never replacing extracted content

### Prepare reusable material packages

- Raw conversion mode outputs a single MarkItDown Markdown file; AI-enhanced mode (default) produces a complete package: `README.md` + `raw.md` + `content.md` + `chunks/` + `assets/` + `manifest.json`
- Word / PowerPoint → PDF conversion for DOC/DOCX/PPT/PPTX, using Microsoft Office when available with a LibreOffice fallback

### Organize creative video assets

- Standardization: compression (high quality / balanced / smallest size), audio extraction (MP3 / lossless WAV), standardized MP4
- Metadata-based naming: by capture time, location, device, and more; GPS coordinates are mapped to readable place names locally and never uploaded
- Deduplication and organization: SHA-256 + duration + resolution duplicate detection; organized copies by year/date/location — originals are never moved or renamed
- Keyframe contact sheets: scene-change keyframes exported as a JPEG overview labeled with source filenames and timestamps, with a first-frame fallback when no scene change is detected

### Reliable batch processing and task management

- Batch processing with per-file failure isolation
- Task center with waiting / running / success / failed / cancelled / interrupted states, independent retry, and recovery after an abnormal exit
- Per-item and overall progress, conservative output-size estimates, and a disk-space preflight that refuses to start when space is insufficient
- Unified processing history with search, filters, and cleanup; 90-day / 512 MB retention by default; history never stores document body content

**What you get** (default output layout):

```text
your chosen output folder\
├── course.pdf                # plain conversion: a single PDF file
├── notes.md                  # raw Markdown: a single file
├── video_compressed.mp4      # plain media processing: a single file
├── course_AI package\        # created only in AI-enhanced mode
│   ├── README.md             # package entry point
│   ├── raw.md                # raw MarkItDown output
│   ├── content.md            # cleaned body text
│   ├── manifest.json         # compact manifest
│   ├── assets\               # only when image resources exist
│   └── chunks\               # only when content is split into multiple segments
└── video_keyframes\          # created only by keyframe analysis
    ├── contact-sheet.jpg
    ├── manifest.json
    └── frames\
```

## Privacy & Safety

- **Local-first**: conversion, cleaning, OCR, metadata reading, and history all run on your machine; no files are uploaded by default.
- **Source files are safe**: they are never overwritten, deleted, moved, or renamed in place; colliding results get `_2`, `_3` suffixes.
- **Network access requires consent**: update checking is off by default and only contacts the GitHub Releases API after you enable it in Settings and click manually. Supplementing a missing tool (ExifTool pinned archive with SHA-256; LibreOffice / FFmpeg via WinGet) shows its source, version, license, and destination before anything is downloaded. Microsoft Office is never downloaded.
- **History stays separate**: processing history lives in the app data directory, away from exported results; deleting history and clearing the cache are separate, confirmed actions, and neither deletes source files.

## Installation

Download from [GitHub Releases](https://github.com/Prad1se/ai-material-preprocessor/releases/latest):

- **Portable ZIP**: extract the whole archive and run `AI-Material-Preprocessor.exe`. Keep `_internal`, `tools`, and the third-party license folders together with the EXE.
- **Installer EXE**: installs for the current user and provides an uninstall entry.

Requirements: Windows x64. By default results are written to an "AI素材处理结果" (AI Material Processing Results) folder next to the source; the name can be changed in Settings. The current release is not commercially code-signed, so Windows SmartScreen may warn about an "unknown publisher"; verify the SHA-256 checksum before continuing.

Run from source:

```powershell
git clone https://github.com/Prad1se/ai-material-preprocessor.git
cd ai-material-preprocessor
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

## Developer Information

Tech stack: Python 3.11+ / PySide6 / MarkItDown / FFmpeg / RapidOCR / ONNX Runtime / PyInstaller.

```powershell
# Run all tests
.\.venv\Scripts\python.exe -m pytest

# Full quality gate (format, lint, types, tests)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_quality.ps1

# Build and verify a release
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\package_release.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_release.ps1 -Version 2.0.0rc1
```

- User configuration lives at `%LOCALAPPDATA%\AI Material Preprocessor\config.json` with versioned, backward-compatible migration; see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
- Architecture and key decisions: [docs/adr/](docs/adr/), [docs/BASELINE_2.0.md](docs/BASELINE_2.0.md).
- Milestone trace: [docs/PROJECT_PROGRESS.md](docs/PROJECT_PROGRESS.md).
- Release notes: [docs/releases/](docs/releases/).
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md); security reports: [SECURITY.md](SECURITY.md).

## License

Application source code is under the [MIT License](LICENSE). Third-party components (MarkItDown, PySide6, RapidOCR, ONNX Runtime, pypdfium2, FFmpeg, and others) remain under their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and `third_party_licenses/`.

The bundled FFmpeg 8.1.2 (Gyan Essentials build) is GPLv3; the corresponding source archive is published alongside the Windows ZIP in each GitHub Release.

The mouse illustrations used in the UI were provided directly by the maintainer; the source materials and processing versions are documented in [`assets/mouse/README.md`](assets/mouse/README.md).
