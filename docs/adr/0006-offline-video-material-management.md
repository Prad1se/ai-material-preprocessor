# ADR 0006: Offline video material management

## Status

Accepted for the 2.0 Release Candidate.

## Context

The existing FFmpeg, ffprobe, and ExifTool adapters already convert media and read embedded
metadata. M4 needs to turn those facts into a safe organization workflow without becoming a video
editor or uploading private GPS coordinates.

## Decision

- Keep ExifTool, ffprobe, and FFmpeg as the metadata and media engines.
- Record which prioritized timestamp field supplied the capture time.
- Resolve friendly places from a user-owned local coordinate dictionary; a manual value always wins.
- Never call an online reverse-geocoding service.
- Organize by copying into date and/or location folders. Never move or rename the source in place.
- Detect duplicates with a streaming SHA-256 digest plus rounded duration and resolution.
- Treat duplicate findings as warnings rather than deleting files.
- Use FFmpeg `showinfo` timestamps from the same keyframe extraction pass and place them beside the
  source filename in contact-sheet captions and the keyframe manifest.
- Keep rename and organization traces in the existing centralized task history.

## Consequences

The workflow remains local and non-destructive. Full-file hashing can make a large batch preview
slower, but it avoids unsafe partial-hash assumptions. A local coordinate dictionary only recognizes
places the user has explicitly entered; unknown coordinates remain visible as coordinates.
