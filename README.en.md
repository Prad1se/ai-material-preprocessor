<div align="center">

# AI Material Preprocessor

### Prepare documents and videos for AI — locally on Windows

**English** · [简体中文](README.md)

[![Tests](https://github.com/Prad1se/ai-material-preprocessor/actions/workflows/tests.yml/badge.svg)](https://github.com/Prad1se/ai-material-preprocessor/actions/workflows/tests.yml)
[![Latest release](https://img.shields.io/github/v/release/Prad1se/ai-material-preprocessor?label=release)](https://github.com/Prad1se/ai-material-preprocessor/releases/latest)
[![Windows](https://img.shields.io/badge/Windows-x64-0078D4?logo=windows)](https://github.com/Prad1se/ai-material-preprocessor/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/code-MIT-yellow.svg)](LICENSE)

**[Download stable release](https://github.com/Prad1se/ai-material-preprocessor/releases/latest)** · **[Explore examples](examples/)** · **[Report an issue](https://github.com/Prad1se/ai-material-preprocessor/issues)**

</div>

AI Material Preprocessor is a local Windows desktop app that turns PDFs, Word documents, PowerPoint decks, spreadsheets, web content, text, and videos into structured, traceable materials for AI or downstream creative work.

- **Doro Documents**: conversion, cleaning, OCR, splitting, provenance, AI Context Packs, and Context Budgets.
- **Mouse Video Workshop**: compression, normalization, audio extraction, metadata naming, deduplication, organization, and keyframe contact sheets.
- **Local first**: files are not uploaded by default, and source material is never overwritten, moved, or deleted.

> **Release status:** the latest stable release is **v2.0.0**. The repository currently contains **v2.1 development work**, including the dual-workspace UI, AI Context Packs, and Source Map experience. Use the Releases page when you need the stable packaged application.

<!-- release-version: 2.0.0 -->

## Two focused workspaces

| Doro Documents | Mouse Video Workshop |
|---|---|
| Reading, knowledge organization, and AI context preparation | Batch media processing and material organization |
| PDF, DOCX, PPTX, XLSX, HTML, TXT, and more | MP4, MOV, MKV, AVI, WebM, and more |
| Markdown, AI-ready document packages, AI Context Packs | Compressed video, normalized MP4, audio, keyframe packages |
| Provenance labels, quality warnings, Source Map | Metadata, place naming, duplicate detection, contact sheets |

Both workspaces share one task center, history repository, settings system, and local execution Core. Switching workspaces does not cancel running tasks.

<table>
  <tr>
    <td width="50%"><strong>Doro Documents</strong></td>
    <td width="50%"><strong>Mouse Video Workshop</strong></td>
  </tr>
  <tr>
    <td><img src="docs/images/github/documents-workspace.png" alt="Chinese Doro Documents workspace"></td>
    <td><img src="docs/images/github/video-workspace.png" alt="Chinese Mouse Video workspace"></td>
  </tr>
</table>

## Get started in 30 seconds

1. Download the installer or portable package from [Releases](https://github.com/Prad1se/ai-material-preprocessor/releases/latest).
2. Open the **Documents** or **Video** workspace and drop in your files, or use the file picker.
3. Choose a preparation mode and review the options for the current job.
4. Select **Prepare documents** or the relevant video action.
5. Open the result. AI Context Packs also provide **Copy for AI** and **View Source Map** actions.

The repository includes synthetic inputs and real pipeline-generated Context Pack outputs under [examples/](examples/), with no private material:

- [Research paper example](examples/research-paper/): PDF page-level provenance.
- [Course material example](examples/course-material/): honest document-level fallback for DOCX, without fabricated page numbers.

## Document capabilities

### Conversion and cleaning

- Convert PDF, DOCX, PPTX, XLSX, HTML, CSV, JSON, XML, TXT, EPUB, and more to Markdown.
- Remove repeated headers, footers, and PowerPoint template text; repair heading levels; normalize code fences and formula markers.
- Preserve tables, fenced code, block formulas, slide boundaries, and worksheet boundaries.
- Optional local OCR supplements extracted text and never replaces it.
- Convert Word and PowerPoint files to PDF through Microsoft Office, with a LibreOffice fallback.

### AI Context Packs (v2.1 development)

An AI Context Pack is more than a renamed Markdown package. It combines multiple documents into a deterministic, inspectable context set:

- **Context Budget** presets for 32K, 64K, 128K, custom values, or no limit.
- Safe splitting at document, section, and paragraph boundaries without silently deleting content to meet a budget.
- Stable `source-001` and block IDs with real page, slide, worksheet, OCR-page, or document-level provenance when available.
- `context-report.json` records estimated tokens, integrity, pack allocation, and overflow warnings.
- **Copy for AI** produces deterministic text without summarizing, rewriting, absolute paths, or binary assets.
- **Source Map v1** traces pack content to available evidence. It offers page-level opening only when supported and otherwise clearly falls back to opening the source document.

Typical output:

```text
AI-Context-Pack\
├── START_HERE.md              # usage order, budget, and warnings
├── content.md                 # complete archive; not a budget-constrained unit
├── manifest.json              # Context Pack v1 manifest
├── context-report.json        # budget, pack, and integrity report
├── packs\
│   ├── 001-context.md         # budget-aware AI upload unit
│   └── 002-context.md
└── sources\
    └── source-001\
        ├── content.md
        └── source-manifest.json
```

Token values are always labeled **Estimated tokens**. They are deterministic, model-independent estimates—not exact ChatGPT, Claude, or other model tokenizer counts.

## Video capabilities

- Compress video with high-quality, balanced, and smallest-size presets.
- Normalize to MP4 and extract MP3 or lossless WAV audio.
- Build readable names from capture time, location, and device metadata; GPS-to-place mapping stays local.
- Use SHA-256, duration, and resolution to assist duplicate detection.
- Create organized copies by year, date, or location without moving or renaming original videos.
- Extract scene-change keyframes and generate JPEG contact sheets labeled with filenames and timestamps.

## Tasks, history, and reliability

- Batch execution with per-file failure isolation.
- Waiting, running, success, failed, cancelled, interrupted, and retry states, with queue recovery after abnormal exit.
- Conservative disk-space preflight before processing starts.
- Searchable, filterable history with 90-day / 512 MB retention by default; document bodies are not stored in history.
- Colliding outputs receive `_2`, `_3`, and later suffixes instead of overwriting existing results.

## Privacy and safety

- Conversion, cleaning, OCR, media processing, and history are local by default.
- Original files are never overwritten, deleted, moved, or renamed in place.
- Update checks are disabled by default and only contact the GitHub Releases API after user opt-in and a manual action.
- Missing-tool setup shows the source, version, license, and destination before installation; Microsoft Office is never downloaded by the app.
- Exported results can contain source filenames and document content. Review them before sharing.

## Installation

### Windows installer or portable package

Open [GitHub Releases](https://github.com/Prad1se/ai-material-preprocessor/releases/latest):

- **Installer EXE**: per-user installation with an uninstall entry.
- **Portable ZIP**: extract the entire archive and run `AI-Material-Preprocessor.exe`. Keep `_internal`, `tools`, and license folders beside the executable.

Windows x64 is required. The current stable release is not commercially code-signed, so Windows SmartScreen may show an “unknown publisher” warning. Verify the published SHA-256 before continuing.

### Run from source

```powershell
git clone https://github.com/Prad1se/ai-material-preprocessor.git
cd ai-material-preprocessor
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

## Development and contribution

Stack: Python 3.11+, PySide6 Widgets, MarkItDown, FFmpeg, RapidOCR, ONNX Runtime, and PyInstaller.

```powershell
# Full quality gate: formatting, lint, types, and tests
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_quality.ps1

# Build and verify release packages
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\package_release.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_release.ps1 -Version 2.0.0
```

- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Architecture decisions](docs/adr/)
- [v2.0 baseline](docs/BASELINE_2.0.md)
- [Release notes](docs/releases/)

## License and artwork

Project-authored source code is licensed under the [MIT License](LICENSE). MarkItDown, PySide6, RapidOCR, ONNX Runtime, pypdfium2, FFmpeg, and other third-party components remain under their respective licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and `third_party_licenses/`.

> Doro and mouse artwork is not covered by the MIT code license. Doro artwork is distributed under the non-commercial-use basis confirmed by the project maintainer; commercial distributions must remove or replace it, or obtain separate permission. See the [Doro asset notice](assets/doro/README.md) and [mouse asset notice](assets/mouse/README.md) for provenance, purpose, and replacement instructions. This notice does not claim ownership of the characters or original artwork.
