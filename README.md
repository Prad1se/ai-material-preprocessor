> [English](README.en.md) | [中文](README.md)

# AI Material Preprocessor

> 把文档和视频一键整理成 AI 能直接读的素材，全程离线运行在本机。

[![Tests](https://github.com/Prad1se/ai-material-preprocessor/actions/workflows/tests.yml/badge.svg)](https://github.com/Prad1se/ai-material-preprocessor/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/Prad1se/ai-material-preprocessor)](https://github.com/Prad1se/ai-material-preprocessor/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

本地 Windows 桌面工具：把 PDF、Word、PPT、Excel、网页与视频等原始素材，整理成 AI 更容易理解和使用的结构化素材。它不是简单格式转换，而是 **转换 + 清洗 + 结构化 + 来源追溯 + AI-ready 输出**。

- 文档 → AI 可读的 Markdown 资料包（清洗、质检、分块、来源追溯、可选本地 OCR）
- 视频 → 便于继续创作的标准素材库（压缩、命名、整理、去重、关键帧联系表）
- 本地优先，文件不出本机，永不覆盖原始文件

**当前状态**：公开稳定版本 **2.0.0rc1**。最新源码已合入新能力（如设置页可一键补充缺失工具），将在下一版本随安装包发布。

<!-- release-version: 2.0.0rc1 -->

<!-- 待补充图片：assets/gallery/hero.png —— Hero 图：Before（混乱的原始文件）→ After（规整的 AI 资料包） -->

## 为什么需要它（Why）

直接把原始文件丢给 AI 时，通常会遇到：

- PDF 是排版而非文本：扫描件没有文字层，AI 直接"读"不到内容。
- PPT 模板文字、页眉页脚跨页重复出现，污染上下文。
- 长文档超出上下文窗口，AI 前后文混乱、理解断层。
- 表格、代码块、公式在转换中变形或丢失，AI 得到残缺信息。
- 内容来源不可追溯，AI 的结论无法核对出自哪一页、哪张幻灯片。

"转成文本"远远不够——AI 需要的是**干净、结构完整、分好块、可定位来源**的正文。视频素材也一样：乱命名、重复、格式不一的原始文件，难以浏览、检索和复用。

## 上手演示（Demo）

### 案例 1：课程资料 → AI 学习资料包（主案例）

<!-- 待补充 GIF：assets/gallery/demo-course.gif -->

- **输入**：一批 PDF / PPT 课程课件
- **处理**：转换为 Markdown → 自动清除重复页眉页脚与模板文字 → 修复标题 → 质量检查 → 按结构分块 →（可选）本地 OCR
- **输出**：AI 学习资料包（`content.md` + `chunks` + `assets` + `manifest.json`），每个分块标注来源页/幻灯片
- **价值**：把整门课直接交给 AI 提问、总结、复习，内容干净且可定位

### 案例 2：论文资料 → 可追溯研究资料包

<!-- 待补充截图：assets/gallery/demo-paper.png -->

- **输入**：PDF 论文
- **处理**：转换 → 质量检查（表格完整性、公式与图片风险）→ 来源映射
- **输出**：带风险定位的 Markdown + 分块来源标签 + 精简 manifest（源文件哈希、工具版本）
- **价值**：建立可核查的研究资料库，AI 的结论可溯源到具体页

### 案例 3：视频素材 → 创作素材库

<!-- 待补充 GIF：assets/gallery/demo-video.gif -->

- **输入**：杂乱命名的视频文件
- **处理**：读取元数据 → 按时间/地点命名 → 去重 → 压缩或标准化 → 提取关键帧
- **输出**：按年/日期/地点整理的素材库 + 关键帧联系表总览
- **价值**：几百条素材几分钟内变成可浏览、可检索、可直接复用的库，原文件不动

## 核心功能（Features）

### 让文档被 AI 真正读懂

- 一键转 Markdown：PDF、Word、PowerPoint、Excel、HTML、CSV、JSON、XML、TXT、EPUB
- 自动清洗：删除跨 3 页以上重复出现的页眉页脚与 PPT 模板文字，修复跳级标题，统一代码围栏与公式标记
- 结构保真：为每张幻灯片与每个工作表补充明确分隔，保持表格、代码块与块公式完整

### 生成可追溯的知识资料包

- 结构感知拆分：按标题与目标长度拆分，默认每段约 4000 token（可在界面调整）；只有内容确实超限时才生成 `chunks`
- 来源追踪：每个分段与每个风险都定位到行号及对应页、幻灯片、工作表或 OCR 页面
- 质量检查：表格损坏、公式可能丢失、图片缺失、标题跳跃等风险一目了然
- 精简 manifest：记录源文件哈希、主要工具版本、来源、分块顺序与警告摘要，不写入本机路径、正文与完整报告
- 可选本地 OCR：识别图片、PDF 页面与 Office 内嵌图片，默认关闭；作为补充文本而不覆盖正文

### 整理可复用的视频素材

- 标准化：视频压缩（高质量 / 均衡 / 体积优先三档）、提取音频（MP3 / 无损 WAV）、标准化 MP4
- 元数据命名：按拍摄时间、地点、设备等规则命名，GPS 坐标在本机映射为易读地名，不上传
- 去重与整理：SHA-256 + 时长 + 分辨率检测重复，按年/日期/地点生成整理副本，原视频不移动、不改名
- 关键帧联系表：按场景变化提取关键帧并生成 JPEG 总览图，标注源文件名与时间戳

### 可靠批处理与任务管理

- 批量处理，单个文件失败不影响其余任务
- 任务中心：等待 / 运行 / 成功 / 失败 / 取消 / 中断，可独立重试，异常退出后自动标记中断并可恢复
- 单项真实进度与批次总体进度，处理前估算输出占用，磁盘空间不足不会启动转换
- 统一历史记录：支持搜索、筛选与清理，默认保留 90 天 / 512 MB，历史不保存素材正文

**你会得到什么**（默认输出结构）：

```text
用户选择的输出目录\
├── 课件.pdf                     # 普通转换：单个 PDF 文件
├── 讲义.md                      # 原始 Markdown：单个文件
├── 视频_compressed.mp4          # 普通媒体处理：单个文件
├── 课件_AI资料包\               # 仅 AI 增强模式创建
│   ├── README.md                # 资料包入口
│   ├── raw.md                   # MarkItDown 原始结果
│   ├── content.md               # 清洗后的正文
│   ├── manifest.json            # 精简清单
│   ├── assets\                  # 仅存在图片资源时生成
│   └── chunks\                  # 仅拆分成两段以上时生成
└── 视频_关键帧包\               # 仅关键帧分析创建
    ├── contact-sheet.jpg
    ├── manifest.json
    └── frames\
```

## 隐私与安全（Privacy）

- **本地优先**：转换、清洗、OCR、元数据读取与历史记录全部在本机完成，默认不上传任何文件。
- **不碰源文件**：永不覆盖、删除、移动或就地重命名原始文件；同名结果自动追加 `_2`、`_3`。
- **联网需确认**：更新检查默认关闭，仅在设置中授权并手动点击时才访问 GitHub Releases。补充缺失工具（ExifTool 固定版本 + SHA-256 校验；LibreOffice / FFmpeg 经 WinGet 安装）前，会展示来源、版本、许可证与保存位置；Microsoft Office 从不下载。
- **历史与输出分离**：历史统一保存在应用数据目录，与导出目录分离；删除历史与删除缓存分开确认，两者都不会删除源文件。

## 安装与使用（Installation）

从 [GitHub Releases](https://github.com/Prad1se/ai-material-preprocessor/releases/latest) 下载：

- **便携版 ZIP**：完整解压后双击 `AI-Material-Preprocessor.exe`。`_internal`、`tools` 与第三方许可目录必须与 EXE 一起保留。
- **安装版 EXE**：安装到当前用户目录，带卸载入口。

系统要求：Windows x64。默认在源文件旁创建 `AI素材处理结果` 目录保存结果，目录名称可在设置中修改。当前版本未进行商业代码签名，Windows SmartScreen 可能显示"未知发布者"，可在校验 SHA-256 后继续。

源码运行：

```powershell
git clone https://github.com/Prad1se/ai-material-preprocessor.git
cd ai-material-preprocessor
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

## 开发者信息（Developer Information）

技术栈：Python 3.11+ / PySide6 / MarkItDown / FFmpeg / RapidOCR / ONNX Runtime / PyInstaller。

```powershell
# 运行全部测试
.\.venv\Scripts\python.exe -m pytest

# 完整质量门（格式、静态检查、类型、测试）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_quality.ps1

# 构建与发布验证
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\package_release.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_release.ps1 -Version 2.0.0rc1
```

- 用户配置位于 `%LOCALAPPDATA%\AI Material Preprocessor\config.json`，带版本兼容迁移，详见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。
- 架构与关键技术决策：[docs/adr/](docs/adr/)、[docs/BASELINE_2.0.md](docs/BASELINE_2.0.md)。
- 里程碑记录：[docs/PROJECT_PROGRESS.md](docs/PROJECT_PROGRESS.md)。
- 发布说明：[docs/releases/](docs/releases/)。
- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)；安全报告：[SECURITY.md](SECURITY.md)。

## 许可证（License）

本项目自写源代码采用 [MIT License](LICENSE)。MarkItDown、PySide6、RapidOCR、ONNX Runtime、pypdfium2、FFmpeg 等第三方组件遵循各自许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 `third_party_licenses/`。

界面使用的鼠鼠图片由项目维护者直接提供，素材来源与处理版本见 [`assets/mouse/README.md`](assets/mouse/README.md)。
