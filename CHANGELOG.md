# Changelog

## Unreleased — 2.0.0 RC development

### M0 architecture baseline

- Add explicit task lifecycle and safe user-facing error types.
- Add an argument-array process adapter with timeout and cancellation support.
- Move operation dispatch out of the Qt worker into document/video application services.
- Split Markdown cleaning, quality checking, structural splitting, and package orchestration.
- Add public synthetic regression fixtures and raise the suite from 80 to 98 passing tests.
- Add Ruff formatting/linting, mypy checking, and matching GitHub Actions quality gates.

### M1 reliable task center

- Add an atomic, versioned task queue with waiting, running, success, failure, cancelled,
  and interrupted states; running tasks from an abnormal exit are recoverable as interrupted.
- Add independent task progress, overall progress, safe waiting/running cancellation, failure
  isolation, and retry for failed, cancelled, interrupted, or recovered waiting tasks.
- Stream FFmpeg's machine-readable progress output without losing captured diagnostics.
- Add conservative disk-space preflight with a configurable safety margin before any converter
  starts.
- Add searchable history with status/operation filters, selected deletion, separate cache deletion,
  full clearing, automatic retention, and a directory size limit.
- Record source/result paths, attempts, timestamps, relevant parameters, and detected tool versions
  without storing private document contents.
- Split the task-center table and history dialog out of the main PySide6 window.
- Raise the suite to 132 passing tests plus one opt-in Office environment test.

### M2 preview and quality experience

- Add typed, read-only document and video preview models outside the main Qt window.
- Show document source information and parameters before processing, then show cleaned Markdown,
  heading structure, chunk lengths, OCR confidence, and content risks in an application-only report.
- Add video metadata previews for capture time, duration, resolution, frame rate, codec, location,
  output name, and a conservative output-size range.
- Add dry-run batch naming with planned collision warnings and no output-directory mutation.
- Warn before lossy video/audio re-encoding and codec changes.
- Display generated contact sheets directly in the application after successful keyframe processing.
- Keep compact quality summaries in central history details without storing Markdown body text.
- Upgrade processing-history manifests to schema version 2 while retaining schema-1 reads.
- Raise the suite to 142 passing tests plus one opt-in Office environment test.

### M3 document provenance and compact AI packages

- Preserve page, slide, worksheet, and OCR source spans with line ranges and confidence metadata.
- Attach source labels to structural Markdown chunks while keeping headings with their content and
  avoiding cuts inside tables, fenced code, and block formulas.
- Add line- and source-aware warnings for missing images, malformed tables, empty source sections,
  heading jumps, unclosed code fences, and possible formula loss.
- Keep original heading-jump findings visible after the cleaner repairs the Markdown structure.
- Replace the verbose package manifest with format version 2 containing source SHA-256, tool
  versions, ordered chunks, assets, provenance, OCR confidence, and compact warning summaries.
- Remove private absolute source paths, full quality reports, target lengths, and verbose logs from
  AI package manifests.
- Raise the suite to 151 passing tests plus one opt-in Office environment test.

### M4 video material management

- Record capture-time priority sources from ExifTool, ffprobe, or file metadata fallbacks.
- Add an offline GPS-to-place dictionary with explicit manual location overrides and no network use.
- Add project and device naming fields while retaining existing date, location, camera, codec, and
  resolution fields.
- Add non-destructive organization copies under date, location, or date-and-location folders.
- Add batch conflict previews for nested destinations and preserve all original files.
- Detect duplicate materials using streaming SHA-256 plus duration and resolution.
- Expand the video metadata preview with GPS, camera, metadata source, and capture-time source.
- Label contact sheets and keyframe manifests with source filenames and FFmpeg scene timestamps.
- Persist project, organization mode, location override, parameters, and tool versions in the
  centralized processing history.
- Raise the suite to 162 passing tests plus one opt-in Office environment test.

## 1.4.0 — 2026-08-04

- 移除首页“本机能力”状态栏；缺失工具只在相关操作需要时提示。
- 转换质量检查改为完成弹窗，不再生成 `quality-report.md/json`。
- AI 资料包保留 `manifest.json`，继续记录来源、质量、资源和拆分索引。
- `chunks` 仅在文档实际拆成两段以上时生成，短文档只保留完整正文。
- 新增历史记录数量与占用统计，以及带二次确认的“清除历史”功能。
- 当前 78 项测试通过，1 项 Office 环境测试按需运行。

## 1.3.1 — 2026-08-04

- 修复 Windows 深色系统主题下，下拉框、下拉项目和文件列表出现白底白字的问题。
- 为文件项目、下拉弹层、选中状态和命名预览表格增加完整的显式配色。
- 新增深色系统调色板 GUI 回归测试；当前 76 项测试通过，1 项 Office 环境测试按需运行。

## 1.3.0 — 2026-08-04

- 重做为 Apple 风格的浅色大圆角界面，重新梳理标题、能力状态、素材区、处理区和输出提示。
- 界面会明确说明当前任务生成“单个文件”还是“AI 资料包 / 关键帧包”。
- PDF、原始 Markdown、压缩视频、音频、标准 MP4 和重命名副本直接写入用户选择的目录，不再创建多余的分类子目录。
- 只有 AI 增强文档和视频关键帧分析会创建包含多个文件的资料包目录。
- 任务 manifest 迁移到 `%LOCALAPPDATA%\AI Material Preprocessor\History`，按年月统一归档，不再污染用户导出目录。
- 历史记录保存输入与输出绝对路径，并可从主界面直接打开。
- 测试增加到 75 项通过，另有 1 项 Office 环境测试按需运行。

## 1.2.0 — 2026-08-01

- 将 AI 资料包、Markdown 清洗、质量报告和 manifest 提升为默认高优先级工作流。
- AI 资料包新增入口 README、来源与文件信息、质量摘要和完整文件清单。
- 新增 FFmpeg 场景关键帧提取、首帧回退、联系表及视频分析清单。
- 命名模板新增日期拆分、坐标、分辨率、时长、编码和相机字段。
- 每次批处理新增任务级 `任务记录/<时间>/manifest.json`。
- 测试增加到 70 项通过，另有 1 项 Office 环境测试按需运行。

## 1.1.0 — 2026-08-01

- 新增“原始转换”和“AI 增强”两种 Markdown 模式。
- 新增连续空行、标题层级、PPT 重复模板文字、幻灯片分隔、Excel 工作表标题、图片路径、代码块与公式清洗。
- 新增转换质量报告、跨语言长度估算、按标题和目标长度拆分，以及分段清单。
- 新增 RapidOCR + ONNX Runtime 本地 OCR，可识别图片、PDF 页面与 Office 内嵌图片；默认关闭。
- 保留 MarkItDown 原始输出，所有增强结果继续写入独立目录。
- 测试增加到 62 项通过，另有 1 项 Office 环境测试按需运行。

## 1.0.0 — 2026-07-31

- 完成 Windows PySide6 桌面应用与 onedir EXE 发布。
- 接入 MarkItDown、Microsoft Office / LibreOffice、FFmpeg、ffprobe / ExifTool 可选元数据链。
- 增加批量处理、动态能力矩阵、命名预览、独立输出和冲突避让。
- 增加单元测试、GUI 测试、真实格式端到端测试和打包后自检。
