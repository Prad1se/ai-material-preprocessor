# Third-Party Notices

AI Material Preprocessor is MIT-licensed application code. It uses and, in the Windows portable release, redistributes third-party components under their own licenses. Those components are not relicensed under MIT.

The release includes applicable license texts under `third_party_licenses/`. Python package metadata retained under `_internal/*dist-info/` may contain additional copyright and license notices.

## Runtime components

| Component | Version used by v2.0.0 | License | Purpose |
|---|---:|---|---|
| Microsoft MarkItDown | 0.1.7 | MIT | Document-to-Markdown conversion |
| PySide6 / Qt for Python | 6.11.1 | LGPLv3 / GPLv3 / commercial | Desktop user interface |
| RapidOCR | 3.9.2 | Apache-2.0 | Local OCR |
| ONNX Runtime | 1.20.1 | MIT | Local OCR model inference |
| pypdfium2 / PDFium | 5.12.1 | Apache-2.0 / BSD-3-Clause and bundled third-party terms | PDF page rendering for OCR |
| FFmpeg / ffprobe Gyan Essentials Build | 8.1.2 | GPLv3 | Media conversion and metadata probing |
| packaging | 26.3 | Apache-2.0 or BSD-2-Clause | Safe release-version comparison |

The bundled FFmpeg build reports `--enable-gpl`, `--enable-version3`, and GPL-covered libraries including libx264. It is therefore distributed under GPLv3. Its exact source commit is `38b88335f9`; the corresponding source archive is published alongside the Windows ZIP in the GitHub Release. See `third_party_licenses/ffmpeg/`.

## Source and build-only components

| Component | License | Purpose |
|---|---|---|
| imageio-ffmpeg | BSD-2-Clause | Source-mode FFmpeg fallback discovery |
| static-ffmpeg | MIT | Build-time FFmpeg / ffprobe acquisition |
| PyInstaller 6.22.0 | GPLv2-or-later with bootloader exception | Windows packaging |
| NSIS 3.12 | zlib/libpng; bundled compression modules have their own terms | Installer generation |
| 7-Zip 26.02 | Public domain / LGPL-2.1-or-later with unRAR restriction | Verified build-time extraction of NSIS; not redistributed |
| pytest 9.1.1 / pytest-qt 4.5.0 | MIT | Tests |

## External applications

Microsoft Office, LibreOffice, and ExifTool are not included by default. After explicit user
confirmation, the application can ask WinGet to install LibreOffice or download the official
ExifTool portable archive with a pinned SHA-256. Those tools remain governed by their own licenses;
Microsoft Office is never downloaded by the application. If a user adds ExifTool to a custom
portable build, ExifTool remains under the Artistic License 1.0 or GPLv1+.

## Upstream links

- MarkItDown: https://github.com/microsoft/markitdown
- Qt for Python: https://doc.qt.io/qtforpython-6/
- RapidOCR: https://github.com/RapidAI/RapidOCR
- ONNX Runtime: https://github.com/microsoft/onnxruntime
- pypdfium2: https://github.com/pypdfium2-team/pypdfium2
- FFmpeg: https://ffmpeg.org/
- Gyan Windows builds: https://www.gyan.dev/ffmpeg/builds/
- NSIS: https://nsis.sourceforge.io/
- 7-Zip: https://www.7-zip.org/

This file is informational and is not legal advice. Refer to the included license texts and upstream projects for the complete terms.
