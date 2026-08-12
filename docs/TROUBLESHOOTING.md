# Troubleshooting

## The application does not start

- Keep the entire portable folder together; do not move only the EXE away from `_internal`.
- Re-download the ZIP or installer and compare it with `SHA256SUMS.txt`.
- Windows SmartScreen may warn because the current release is not commercially code-signed.
- Start the EXE with `--self-test <empty-output-folder>` to create a local diagnostics report.

## A conversion tool is missing

Open **Settings → Local capabilities** and choose **Re-detect**. Missing ExifTool, LibreOffice, or
FFmpeg capabilities show a supplement button. Before downloading, the application displays the
source, version, license, and destination and asks for network consent. You can select a custom
tool directory or executable path. Microsoft Office is never downloaded by the application.

## Word or PowerPoint cannot create PDF

Install Microsoft Office or LibreOffice, close files already open in those programs, and retry.
The source remains unchanged after a failure.

## Markdown quality is lower than expected

Use enhanced mode, inspect the preview and quality dialog, and enable local OCR only for scanned
pages. Complex diagrams, equations, and visual slide relationships should also be retained as PDF
or images for a vision-capable model.

## Video processing fails

Check available disk space and the error shown in task history. Corrupted or unusual codecs may
require a newer FFmpeg build. Partial outputs are removed; original videos are not modified.

## Where configuration and history are stored

User configuration and history are under `%LOCALAPPDATA%\AI Material Preprocessor`. Exported
results are separate. Clearing history never deletes source files.
