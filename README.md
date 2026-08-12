# AI 素材预处理工具

Windows 本地桌面工具，用于把常见文档准备成 AI 易读的 Markdown，并把视频准备成便于继续创作的标准素材。

[![Tests](https://github.com/Prad1se/ai-material-preprocessor/actions/workflows/tests.yml/badge.svg)](https://github.com/Prad1se/ai-material-preprocessor/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/Prad1se/ai-material-preprocessor)](https://github.com/Prad1se/ai-material-preprocessor/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

当前版本：**2.0.0rc1**

2.0 RC1 已完成 M0–M6：架构基线、可靠任务中心、预览质量、来源追溯、视频素材管理、首次引导和可复现 Windows 发布流水线。正式公开 Release 仅在全部本地与 GitHub 检查通过后创建。

## 直接使用

从 [GitHub Releases](https://github.com/Prad1se/ai-material-preprocessor/releases/latest) 下载：

```text
AI-Material-Preprocessor-v2.0.0rc1-windows-x64.zip
AI-Material-Preprocessor-v2.0.0rc1-windows-x64-setup.exe
```

安装版会安装到当前用户目录并创建卸载入口；便携 ZIP 需要完整解压后双击：

```text
AI-Material-Preprocessor.exe
```

便携版是 onedir 发布包，`_internal`、`tools` 和第三方许可目录必须与 EXE 一起保留。程序完全在本机处理文件，不需要上传素材。更新检查默认关闭，只有在设置中授权并手动点击时才访问 GitHub Releases；详见 [PRIVACY.md](PRIVACY.md)。RC1 未进行商业代码签名，Windows SmartScreen 可能显示“未知发布者”。

## 已完成功能

### AI 资料包

通过 Microsoft MarkItDown Python API 转换为 Markdown：

- Word：DOCX
- PowerPoint：PPTX
- Excel：XLSX
- PDF
- HTML / HTM
- CSV、JSON、XML、TXT、EPUB

Markdown 是供 AI、检索和知识库使用的派生副本，不用于还原原文档视觉排版。

提供两种模式：

- **AI 增强**（默认）：生成完整 AI 资料包，保留 MarkItDown 原始结果，并继续清洗、质检和按长度拆分。
- **原始转换**：只输出 MarkItDown 的原始 Markdown，适合需要自行处理的场景。

AI 增强模式会执行：

- 清理连续空行，修复跳级标题。
- 删除跨 3 页以上重复出现的页眉、页脚或 PPT 模板文字。
- 为 PPT 幻灯片增加明确分隔，为 Excel 补充“工作表”一级标题。
- 统一代码围栏与常见行内/块公式标记。
- 将可访问的本地图片复制到 `assets`，并改写为相对路径。
- 完成后以弹窗显示质量检查结果，不在资料包中生成额外报告文件。
- 质量弹窗可查看清洗后 Markdown、标题结构、拆分顺序与预计长度、OCR 置信度及风险定位。
- 仅在内容确实需要拆成两段以上时，按标题与目标长度生成 `chunks`。
- 生成 `README.md` 作为资料包入口，说明 AI 应优先读取正文还是分段。
- 在精简版 `manifest.json` 中记录源文件哈希、主要工具版本、页/幻灯片/工作表来源、
  资源、分段顺序和重要警告摘要；不写入本机绝对路径、完整质量报告或大段日志。
- 每个风险可定位到 Markdown 行号及对应页面、幻灯片、工作表或 OCR 页面。
- 分段尽量保持标题与正文、表格、代码块和块公式完整，并记录每段涉及的来源标签。

默认目标是每段约 4000 个估算 token、硬上限 6000。这里使用跨语言确定性估算，不冒充某个特定模型的精确 tokenizer；目标长度可在界面调整。

### 可选本地 OCR

AI 增强模式可开启 RapidOCR：

- 图片：直接识别。
- PDF：由 pypdfium2/PDFium 在本地渲染每页后识别。
- DOCX / PPTX / XLSX：提取压缩包中的内嵌图片后识别。

OCR 使用 ONNX Runtime 和本地中英文模型，不上传文件，默认关闭。OCR 结果作为“补充文本”附加，不替换 MarkItDown 已提取的正文；图表的空间关系与复杂公式仍需人工或视觉模型复核。

### 普通文档转换

- DOC / DOCX → PDF
- PPT / PPTX → PDF
- 优先调用本机 Microsoft Word / PowerPoint
- 本机没有对应 Office 应用时回退到 LibreOffice headless
- 每个输入直接生成一个 PDF 文件到所选目录，不附带任务记录或额外包装目录

### 准备创作

- 视频压缩：H.264 + AAC，提供高质量、均衡、体积优先三个档位
- 提取音频：MP3 或无损 WAV
- 标准化 MP4：H.264、yuv420p、AAC、Fast Start
- 按场景变化提取关键帧，并生成一张可快速浏览的 JPEG 联系表
- 关键帧结果附带独立 `manifest.json`；无明显切镜时自动回退到首帧
- 按 `{date}_{time}_{location}_{index}` 规则生成视频副本
- 支持 `{project}` / `{device}` 等项目与设备命名字段，并可在处理前手动修正地点
- 通过完全本地的坐标地点词典将常用 GPS 坐标映射为易读名称，不上传坐标
- 可按“年 / 日期 / 地点”目录保存整理副本；原视频不移动、不就地改名
- 使用 SHA-256、时长和分辨率组合检测批量中的重复素材
- 处理前可预览拍摄时间及其来源、时长、分辨率、帧率、编码、GPS、设备、元数据来源、
  地点、最终文件名与预计输出体积
- 批量命名预览会提前标记批次内重名并追加编号，试运行不会创建目录或修改文件
- 压缩、标准化及有损音频输出会在执行前显示质量风险
- 关键帧联系表和清单会标出源文件名及 `HH:MM:SS.mmm` 时间戳，完成后直接在应用内预览
- 支持批量处理；单个文件失败不会中断其余任务
- 任务中心为每个文件显示等待、运行、成功、失败、取消或中断状态
- 视频转换直接读取 FFmpeg 的机器进度流，显示单项真实进度与批次总体进度
- 可取消等待任务，并尽可能安全终止正在运行的 Office、FFmpeg、ffprobe、ExifTool 或 MarkItDown CLI 进程
- 失败、取消和异常中断任务可以独立重试；应用异常退出后，运行中的任务会明确标记为“已中断”
- 执行前按操作保守估算输出占用，并预留安全空间；空间不足时不会启动转换器
- 只有关键帧与联系表会生成多文件资料包；其他音视频操作直接生成单个结果文件
- 每次处理都会在统一历史目录写入输入输出、状态、时间、尝试次数、关键参数和已检测工具版本
- 历史窗口支持搜索以及按状态、操作筛选，可删除所选记录或清空全部历史
- 历史详情保留质量分、预计长度、拆分数、OCR 摘要和风险，不保存 Markdown 正文
- 历史记录与预览缓存分开确认删除；任何历史操作都不会删除源文件或正式输出
- 默认保留 90 天且限制为 512 MB，启动和每批处理结束后自动执行边界清理

视频处理使用项目随附的 FFmpeg。元数据读取顺序为：

1. ExifTool（若用户安装或在配置中指定）
2. ffprobe（若可用）
3. FFmpeg `ffmetadata`
4. 文件修改时间

若视频只有 GPS 坐标，程序保留坐标形式；可在界面手动输入“杭州西湖”等易读地点。程序不会把位置上传到在线地图服务。

## 安全原则

- 永不覆盖、删除或就地重命名原文件。
- 默认在原文件旁创建 `AI素材处理结果`。
- 同名结果自动追加 `_2`、`_3`。
- 失败的 FFmpeg 派生文件会被清理。
- 外部工具通过参数数组调用，不拼接 shell 命令。
- Office 转换以只读方式打开源文档。

默认输出结构：

```text
用户选择的输出目录\
├── 课件.pdf                       # 普通转换：单个文件
├── 讲义.md                        # 原始 Markdown：单个文件
├── 视频_compressed.mp4            # 普通媒体处理：单个文件
├── 课件_AI资料包\                 # 仅 AI 增强模式创建
│   ├── README.md
│   ├── raw.md
│   ├── content.md
│   ├── manifest.json
│   ├── assets\                       # 仅存在图片资源时生成
│   └── chunks\                       # 仅实际拆成两段以上时生成
└── 视频_关键帧包\                 # 仅关键帧分析创建
    ├── contact-sheet.jpg
    ├── manifest.json
    └── frames\
```

任务历史不写入上述目录，而统一存放在：

```text
%LOCALAPPDATA%\AI Material Preprocessor\History\年\月\时间-task-id\manifest.json
```

## 配置

首次启动会解释本地隐私约束并检测工具；之后可通过主界面的“设置”重新检测、选择自定义可执行文件、补充 ExifTool / LibreOffice / FFmpeg、选择工具保存目录、切换浅色/深色/跟随 Windows 主题，以及调整历史保留期限。每次下载前都会显示来源、版本、许可证和保存位置，只有用户确认后才联网。用户设置保存在：

```text
%LOCALAPPDATA%\AI Material Preprocessor\config.json
```

发布包旁的 `config.json` 仅作为旧版兼容和默认模板；首次迁移不会修改该文件。配置可设置输出目录名称、统一历史目录、工具绝对路径和视频默认参数：

```json
{
  "app": {
    "schema_version": 4,
    "onboarding_completed": true,
    "theme": "system",
    "update_check_enabled": false
  },
  "output_folder_name": "AI素材处理结果",
  "history_directory": "",
  "tools": {
    "ffmpeg": "",
    "ffprobe": "",
    "exiftool": "",
    "libreoffice": ""
  },
  "tool_management": {
    "install_directory": "D:/AI-Tools/AI-Material-Preprocessor"
  },
  "video": {
    "compression_crf": 23,
    "compression_preset": "medium",
    "audio_format": "mp3",
    "audio_bitrate": "192k",
    "rename_template": "{date}_{time}_{location}_{index}",
    "project_name": "",
    "organize_mode": "date_location",
    "location_dictionary": {
      "30.2512,120.1693": "杭州西湖"
    },
    "scene_threshold": 0.3,
    "max_keyframes": 24,
    "contact_sheet_columns": 4
  },
  "document": {
    "mode": "enhanced",
    "split_enabled": true,
    "target_tokens": 4000,
    "max_tokens": 6000,
    "ocr_enabled": false
  },
  "task_center": {
    "state_directory": "",
    "disk_space_safety_mb": 512
  },
  "history": {
    "retention_days": 90,
    "max_size_mb": 512
  }
}
```

可用命名字段：

- 基础：`{date}`、`{time}`、`{datetime}`、`{index}`、`{original}`、`{location}`
- 日期：`{year}`、`{month}`、`{day}`、`{hour}`、`{minute}`、`{second}`
- 视频：`{resolution}`、`{width}`、`{height}`、`{duration_s}`、`{codec}`
- 设备：`{camera}`、`{make}`、`{model}`、`{metadata_source}`
- 项目与设备别名：`{project}`、`{device}`
- 坐标：`{latitude}`、`{longitude}`，输出为 `30.2512N`、`120.1693E` 等适合文件名的形式

部分字段依赖 ExifTool 或 ffprobe 中确实存在相应元数据；缺失字段会自动从名称中收缩，不留下连续分隔符。

## 源码运行

```powershell
git clone https://github.com/Prad1se/ai-material-preprocessor.git
cd ai-material-preprocessor
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

首次运行会创建项目自己的 `.venv`，安装 PySide6、MarkItDown、imageio-ffmpeg、测试与打包依赖。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

完整工程质量门（格式、静态检查、类型和全部测试）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_quality.ps1
```

测试包括：

- 能力矩阵、工具查找优先级、版本异常与自定义路径
- 首次启动、图形化设置、配置迁移、文件夹拖入和深浅主题
- 配置合并与 UTF-8 保存
- Windows 安全文件名、命名模板和冲突避让
- ExifTool、ffprobe、FFmpeg 元数据回退
- FFmpeg 命令及进度解析
- GUI 动态操作、设置项可见性和混合批次保护
- 真实 HTML、PPTX、XLSX → Markdown
- 真实 FFmpeg 视频压缩、音频提取、MP4 标准化和安全命名
- 真实 FFmpeg 场景关键帧提取、无场景回退和联系表生成
- 真实 DOCX → PDF → Markdown（通过环境变量提供文档）
- Markdown 清洗、质量报告、长度估算、分段与图片路径修复
- RapidOCR 适配器、真实本地图片 OCR、真实 PPT/XLSX 增强输出
- AI 资料包与文档级 / 任务级 manifest 清单
- 持久任务队列、异常恢复、等待 / 运行取消、失败隔离与重试
- 磁盘空间预检、真实 FFmpeg 单项进度与总体进度
- 历史搜索筛选、选择删除、缓存分离、保留期限与容量上限
- 文档结构 / OCR / 风险预览、视频体积估算、批量命名试运行和应用内历史质量详情

运行 Office 端到端测试：

```powershell
$env:AI_MATERIAL_E2E_DOCX = "D:\path\sample.docx"
.\.venv\Scripts\python.exe -m pytest tests\test_e2e_local.py -rs
```

## 构建与发布验证

构建：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
```

验证打包后的 MarkItDown 和 FFmpeg：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_release.ps1 -Version 2.0.0rc1
```

生成便携 ZIP、当前用户安装程序、FFmpeg 对应源码包和 SHA-256 校验文件：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\package_release.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_installer.ps1 -Version 2.0.0rc1
```

发布产物位于 `release\v2.0.0rc1`。Actions 只构建和验证产物，不会未经确认自动创建公开 Release。故障处理见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

也可直接调用 EXE 自检：

```powershell
.\dist\AI-Material-Preprocessor\AI-Material-Preprocessor.exe --self-test .\work\diagnostics
```

自检结果写入 `diagnostics.json`。

## 项目结构

```text
src\ai_material_preprocessor\
├── capabilities.py       # 文件与可执行操作矩阵
├── errors.py             # 稳定错误代码、用户提示与技术诊断分离
├── infrastructure\       # 可超时、可取消的外部进程适配器
├── converters\           # MarkItDown、Office、FFmpeg 适配器
├── services\             # 应用服务、任务分发、配置、元数据和文件安全
│   ├── document_service.py      # 文档转换用例
│   ├── video_service.py         # 视频处理用例
│   ├── job_executor.py          # 与 GUI 无关的批次分发与失败隔离
│   ├── document_enhancement.py  # AI 资料包编排
│   ├── markdown_cleaning.py     # Markdown 清洗和资源路径
│   ├── markdown_quality.py      # 质量检查
│   ├── markdown_splitting.py    # 结构感知拆分
│   ├── document_provenance.py   # 页面、幻灯片、工作表和 OCR 来源映射
│   ├── preview.py               # 文档与视频只读预览、风险和体积估算
│   ├── video_management.py      # 离线地点、整理计划和重复检测
│   ├── input_discovery.py       # 文件与文件夹拖入、格式过滤和去重
│   ├── tool_capabilities.py     # 工具健康状态与功能安装指引
│   ├── tool_versions.py         # 有超时的本地版本检测
│   └── ocr.py             # RapidOCR、Office 图片提取与 PDF 页面渲染
├── ui\                    # 欢迎页、设置、工具状态、任务中心、预览、历史和主题
├── diagnostics.py        # 发布包自检
└── gui.py                # PySide6 窗口与交互

tests\                    # 单元、GUI 与本地端到端测试
scripts\                  # Office 转换、工具准备、构建和发布验证
docs\adr\                 # 关键技术决策
```

成熟工具选型依据见 `docs\adr\0001-tooling-strategy.md`，2.0 架构边界见
`docs\adr\0002-architecture-and-quality-gates.md`，任务、预览与文档追溯决策见后续 ADR，许可说明见
`THIRD_PARTY_NOTICES.md`。

## 许可证

本项目自行编写的源代码采用 [MIT License](LICENSE)。MarkItDown、PySide6、RapidOCR、ONNX Runtime、pypdfium2、FFmpeg 等第三方组件继续遵循各自许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `third_party_licenses/`。

界面使用的鼠鼠图片由项目维护者直接提供并确认可修改、再分发及商业使用，素材来源和处理版本说明见 [`assets/mouse/README.md`](assets/mouse/README.md)。

Windows 便携包附带的 FFmpeg 8.1.2 Gyan Essentials Build 使用 GPLv3；对应源码压缩包会作为同一 GitHub Release 的独立附件发布。
