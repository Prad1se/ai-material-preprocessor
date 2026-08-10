# ADR 0004: Read-only previews and compact quality history

## Status

Accepted for M2.

## Context

Users need to understand a conversion before it starts and inspect document quality after it finishes.
Previewing must not create output directories, modify source files, or duplicate large Markdown bodies
inside long-lived history. Video output size is inherently uncertain before encoding.

## Decision

- Use immutable preview dataclasses for source files, risks, headings, chunks, OCR pages, documents,
  and videos.
- Keep preview calculation in an application service; Qt dialogs only render typed results.
- Reuse cleaned Markdown, quality, splitting, ffprobe/ExifTool metadata, and naming services instead of
  creating alternate parsing paths.
- Treat video output size as an explicitly labelled conservative range, not an exact promise.
- Perform batch rename preview entirely in memory and reserve planned names to expose collisions.
- Show full Markdown previews only in memory. Persist only scores, counts, OCR confidence summaries,
  and risk messages in the central history manifest.
- Keep conversion reports inside the application. Export directories receive no extra report files.

## Consequences

- Preview behavior is testable without launching external converters or writing user outputs.
- History stays useful and bounded without accumulating document contents.
- Exact output size remains unavailable until an encoder finishes; the UI must preserve that caveat.
- MarkItDown content preview is available after conversion, while the preflight dialog focuses on source
  information and the exact parameters that will be used.
