# ADR 0001：复用成熟转换引擎

状态：已接受
日期：2026-07-31

## 决策

- 文档到 Markdown 使用 Microsoft MarkItDown Python API，并安装 DOCX、PPTX、XLSX、PDF 等可选依赖。
- Word / PowerPoint 到 PDF 优先使用本机 Microsoft Office；LibreOffice headless 作为替代后端。
- 媒体转码、探测与进度使用 FFmpeg / ffprobe。
- 视频拍摄时间、GPS 和地点标签优先使用 ExifTool；缺失时回退到 ffprobe，再回退到文件修改时间。
- Windows EXE 使用 PyInstaller onedir 发布；FFmpeg 与 ffprobe 通过 static-ffmpeg 在构建阶段获取并作为发布目录中的伴随工具，ExifTool 仍为可选工具。
- Markdown 增强采用本地、确定性规则；不重写 MarkItDown 的格式解析器，并始终保留原始 Markdown。
- 可选 OCR 使用 RapidOCR + ONNX Runtime；PDF 页面渲染使用宽松许可的 pypdfium2/PDFium。OCR 默认关闭，不调用云端服务。

## 原因

这些工具分别是各自领域中成熟、可验证且可从命令行或 Python 稳定集成的实现。本项目只负责安全工作流、用户界面、能力检测、命名规则和输出组织，不重新实现格式解析器或编解码器。

## 约束

- 原文件不可覆盖、删除或就地改名。
- 所有外部命令使用参数数组，不拼接 shell 字符串。
- 地点解析默认保持本地。若只有 GPS 坐标，显示坐标并允许用户输入地点，不自动上传位置数据。
- 发布包必须附带第三方工具与许可证说明。
- “token 长度”是跨模型估算值，目标值和硬上限必须可配置，界面不得宣称存在适用于所有模型的绝对最佳长度。

## 依据

- MarkItDown 官方说明其输出面向 LLM，并提供 Python API 与按格式安装的可选依赖。
- FFmpeg 官方提供机器可读的 `-progress` 输出；ffprobe 可用 JSON 输出容器及流元数据。
- ExifTool 官方支持 JSON 读取和视频内嵌 GPS 元数据。
- Microsoft Office 官方提供 Word `ExportAsFixedFormat` 与 PowerPoint `SaveAs` PDF 自动化接口。
- PyInstaller 官方支持 Windows onedir/onefile 以及附加二进制文件。
