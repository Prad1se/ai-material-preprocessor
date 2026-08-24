# ADR 0010: Deterministic Video AI Pack v1

## Status

Accepted for post-2.0 development.

## Context

The Video Workspace already provides independent audio extraction and deterministic scene-change
keyframes, but those outputs do not form one traceable multi-source package. A local package for
multimodal AI use must preserve real timestamps and source identity without claiming semantic video
understanding or copying large original videos by default.

## Decision

- Add `VIDEO_AI_PACK` as an additive Video operation inside the existing application and release
  architecture.
- Represent one ordered group of videos as one persisted multi-source `Job`; assign pack-local IDs
  `video-001`, `video-002`, and so on from that order.
- Build the package in a Qt-independent service and route it through a dedicated executor registry
  entry. Keep all previous Video operations on the existing executor.
- Reuse the existing FFmpeg scene-change command, `showinfo` timestamps, first-frame fallback, contact
  sheet renderer, audio process boundary, and collision-safe path convention.
- Publish a separate `video_ai_pack` schema at version 1. Do not modify the existing
  `video_keyframes`, Context Pack, queue, history, or config schema versions.
- Write every artifact beside the final destination in a controlled temporary directory, validate
  IDs, paths, ordering, status, declared files, and source hashes, then atomically publish it.
- Do not copy original videos. Audio is WAV/PCM 16-bit by default; compressed H.264/AAC proxy video
  is opt-in and explicitly lossy.
- Keep public pack metadata relative and privacy-safe. Embedded GPS may be retained only as local
  source metadata and is never sent to an online lookup service.

## Consequences

The package is deterministic except for `created_at`, while frame count remains dependent on the
existing deterministic scene-change extraction. Missing audio and optional proxy failures are
warnings; cancellation and any failure that prevents core frame/contact-sheet or integrity
completion remove the temporary package. The timeline is per-source artifact provenance, not a
semantic scene model or one continuous multi-video clock.
