# ADR 0009: User-consented tool supplementation

## Status

Accepted after 2.0.0rc1.

## Context

The first-run and settings pages could detect missing tools and accept custom executable paths, but
users still had to leave the application and install every optional capability manually. Automatic
installation must not silently access the network, write large packages to an unexpected drive, or
replace mature package managers and installers.

## Decision

- Keep MarkItDown and local OCR inside the packaged application and keep Microsoft Office outside
  application-managed installation.
- Offer an explicit supplement action only for known, allow-listed tools.
- Show purpose, source, version, license, and destination before requesting network consent.
- Download the fixed ExifTool portable archive from its official release location, pin SHA-256,
  reject unsafe ZIP paths, stage extraction, and retain previous versions on failure.
- Delegate LibreOffice and FFmpeg installation to WinGet with exact package identifiers, argument
  arrays, timeouts, cancellation, package/source agreement flags, and the configured install
  location.
- Set the child installer's temporary download directory to the selected managed-tool root, while
  acknowledging that Windows Package Manager and MSI may still maintain system-managed metadata.
- Let users choose the managed-tool directory; mutable configuration remains under LocalAppData.
- Re-detect capabilities and persist only resolved executable paths after success.

## Consequences

The common missing capabilities can be restored from the graphical interface without adding
parsers, codecs, or Office renderers to this repository. WinGet packages may still display Windows
elevation prompts, and an installer may ignore a requested custom location; the application reports
the detected final path instead of claiming a location it cannot verify.
