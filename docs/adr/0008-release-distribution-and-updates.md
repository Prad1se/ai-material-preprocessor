# ADR 0008: Release distribution and update checks

## Decision

Distribute 2.0 as both a PyInstaller onedir portable ZIP and a current-user NSIS installer. Pin the
NSIS 3.12 installer, the 7-Zip 26.02 installer, and the standalone 7zr.exe bootstrap by SHA-256.
Extract the build tools into the ignored workspace build directory without installing them on the
user's system. Create sorted timestamp-normalized ZIPs, verify the actual archive by extracting it,
run self-test and GUI smoke checks, verify install and uninstall, and generate SHA-256 for every
published artifact.

Update checking remains disabled by default. A user must enable it in Settings and manually start
the request. Only the public GitHub Releases API is contacted; no file or metadata is uploaded.

## Rationale

NSIS is mature, actively maintained, supports unattended CI, and its official license permits
commercial use. It avoids depending on a hosted installer service or introducing administrator
rights. PyInstaller keeps Python and runtime libraries self-contained for users without Python.
The official NSIS installer is not reliably suitable for unattended bootstrap on every Windows
configuration, so the pinned build-only 7-Zip tools provide a deterministic extraction path. They
are not redistributed in the application packages.

## Consequences

The unsigned installer may trigger SmartScreen. FFmpeg GPL source must continue to be published
beside binaries. Release tags must match every declared version before publication. GitHub Actions
builds and validates artifacts but does not make a public Release without a separate approval.
