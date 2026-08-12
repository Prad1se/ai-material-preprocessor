from __future__ import annotations

import hashlib
import os
import shutil
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Protocol
from zipfile import BadZipFile, ZipFile

from ..errors import ErrorCode, UserFacingError
from ..infrastructure.processes import CancellationToken, CommandRequest, ProcessRunner


class InstallMethod(StrEnum):
    PORTABLE_ARCHIVE = "portable_archive"
    WINGET = "winget"


@dataclass(frozen=True)
class ToolInstallSpec:
    key: str
    display_name: str
    method: InstallMethod
    version: str
    description: str
    source_url: str
    license_name: str
    license_url: str
    sha256: str = ""
    archive_executable: str = ""
    installed_executable: str = ""
    package_id: str = ""
    action_label: str = "一键补充"


@dataclass(frozen=True)
class ToolInstallResult:
    key: str
    version: str
    executable_path: Path | None
    tool_paths: Mapping[str, Path]
    restart_required: bool = False


class Runner(Protocol):
    def run(self, request: CommandRequest, **kwargs): ...


Downloader = Callable[..., None]
ExecutableLookup = Callable[[str], str | None]


EXIFTOOL_VERSION = "13.59"
EXIFTOOL_SHA256 = "44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec"

DEFAULT_TOOL_SPECS: dict[str, ToolInstallSpec] = {
    "exiftool": ToolInstallSpec(
        key="exiftool",
        display_name="ExifTool",
        method=InstallMethod.PORTABLE_ARCHIVE,
        version=EXIFTOOL_VERSION,
        description="读取视频拍摄时间、GPS 和设备信息。",
        source_url=(
            "https://sourceforge.net/projects/exiftool/files/"
            f"exiftool-{EXIFTOOL_VERSION}_64.zip/download"
        ),
        license_name="Artistic License / GPL",
        license_url="https://exiftool.org/",
        sha256=EXIFTOOL_SHA256,
        archive_executable="exiftool(-k).exe",
        installed_executable="exiftool.exe",
        action_label="一键补充",
    ),
    "libreoffice": ToolInstallSpec(
        key="libreoffice",
        display_name="LibreOffice",
        method=InstallMethod.WINGET,
        version="current",
        description="Microsoft Office 不可用时用于 Word/PPT 转 PDF。",
        source_url="https://www.libreoffice.org/download/",
        license_name="MPL-2.0",
        license_url="https://www.libreoffice.org/licenses/",
        package_id="TheDocumentFoundation.LibreOffice",
        action_label="通过 WinGet 安装",
    ),
    "ffmpeg": ToolInstallSpec(
        key="ffmpeg",
        display_name="FFmpeg / ffprobe",
        method=InstallMethod.WINGET,
        version="current",
        description="修复视频转换、元数据和联系表所需的本地组件。",
        source_url="https://ffmpeg.org/",
        license_name="GPL-3.0",
        license_url="https://ffmpeg.org/legal.html",
        package_id="Gyan.FFmpeg",
        action_label="通过 WinGet 修复",
    ),
}


def default_tool_install_root(environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    local_app_data = values.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / "AI Material Preprocessor" / "tools"


def configured_tool_install_root(config: Mapping[str, object]) -> Path:
    raw = config.get("tool_management")
    if isinstance(raw, Mapping):
        configured = str(raw.get("install_directory", "")).strip()
        if configured:
            return Path(configured).expanduser().resolve()
    return default_tool_install_root()


def _download_file(
    url: str,
    destination: Path,
    *,
    cancellation: CancellationToken | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "AI-Material-Preprocessor/2"})
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            received = 0
            while chunk := response.read(1024 * 1024):
                if cancellation and cancellation.is_cancelled:
                    raise UserFacingError(
                        ErrorCode.CANCELLED,
                        "工具补充已取消，现有能力没有改动。",
                        retryable=True,
                    )
                out.write(chunk)
                received += len(chunk)
                if on_progress and total:
                    on_progress(min(99, round(received * 100 / total)))
    except UserFacingError:
        destination.unlink(missing_ok=True)
        raise
    except (OSError, urllib.error.URLError) as exc:
        destination.unlink(missing_ok=True)
        raise UserFacingError(
            ErrorCode.DOWNLOAD_FAILED,
            "下载工具失败，请检查网络后重试。",
            technical_detail=f"{type(exc).__name__}: {exc}",
            retryable=True,
        ) from exc


def _safe_extract(archive_path: Path, destination: Path) -> None:
    try:
        with ZipFile(archive_path) as archive:
            members = archive.infolist()
            for member in members:
                normalized = member.filename.replace("\\", "/")
                path = PurePosixPath(normalized)
                if path.is_absolute() or ".." in path.parts or not path.parts:
                    raise UserFacingError(
                        ErrorCode.INTEGRITY_FAILED,
                        "工具压缩包包含不安全路径，已停止安装。",
                    )
            for member in members:
                relative = Path(*PurePosixPath(member.filename.replace("\\", "/")).parts)
                output = destination / relative
                if member.is_dir():
                    output.mkdir(parents=True, exist_ok=True)
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, output.open("wb") as target:
                    shutil.copyfileobj(source, target)
    except BadZipFile as exc:
        raise UserFacingError(
            ErrorCode.INTEGRITY_FAILED,
            "下载的工具压缩包已损坏，已停止安装。",
        ) from exc


class ToolInstaller:
    def __init__(
        self,
        *,
        install_root: Path | None = None,
        specs: Mapping[str, ToolInstallSpec] = DEFAULT_TOOL_SPECS,
        downloader: Downloader = _download_file,
        runner: Runner | None = None,
        executable_lookup: ExecutableLookup = shutil.which,
    ) -> None:
        self.install_root = (install_root or default_tool_install_root()).resolve()
        self.specs = dict(specs)
        self.downloader = downloader
        self.runner = runner or ProcessRunner()
        self.executable_lookup = executable_lookup

    def install(
        self,
        key: str,
        *,
        cancellation: CancellationToken | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> ToolInstallResult:
        if cancellation and cancellation.is_cancelled:
            raise UserFacingError(
                ErrorCode.CANCELLED,
                "工具补充已取消，现有能力没有改动。",
                retryable=True,
            )
        try:
            spec = self.specs[key]
        except KeyError as exc:
            raise UserFacingError(
                ErrorCode.UNSUPPORTED_INPUT,
                "当前能力不支持应用内补充，请查看安装说明。",
            ) from exc
        if spec.method is InstallMethod.PORTABLE_ARCHIVE:
            return self._install_portable(spec, cancellation, on_progress)
        return self._install_winget(spec, cancellation, on_progress)

    def _install_portable(
        self,
        spec: ToolInstallSpec,
        cancellation: CancellationToken | None,
        on_progress: Callable[[int], None] | None,
    ) -> ToolInstallResult:
        target = self.install_root / spec.key / spec.version
        executable = target / spec.installed_executable
        if executable.is_file():
            return ToolInstallResult(spec.key, spec.version, executable, {spec.key: executable})

        download = self.install_root / "_downloads" / f"{spec.key}-{spec.version}.zip"
        download.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(download.read_bytes()).hexdigest() if download.is_file() else ""
        if digest.lower() != spec.sha256.lower():
            download.unlink(missing_ok=True)
            self.downloader(
                spec.source_url,
                download,
                cancellation=cancellation,
                on_progress=on_progress,
            )
            digest = hashlib.sha256(download.read_bytes()).hexdigest()
        if digest.lower() != spec.sha256.lower():
            download.unlink(missing_ok=True)
            raise UserFacingError(
                ErrorCode.INTEGRITY_FAILED,
                "下载文件的 SHA-256 校验失败，已停止安装。",
                technical_detail=f"expected {spec.sha256}; received {digest}",
                retryable=True,
            )

        tool_root = self.install_root / spec.key
        tool_root.mkdir(parents=True, exist_ok=True)
        staging = tool_root / f".staging-{spec.version}-{uuid.uuid4().hex}"
        try:
            raw = staging / "raw"
            raw.mkdir(parents=True)
            _safe_extract(download, raw)
            matches = list(raw.rglob(spec.archive_executable))
            if len(matches) != 1:
                raise UserFacingError(
                    ErrorCode.INTEGRITY_FAILED,
                    "工具压缩包结构与预期不一致，已停止安装。",
                )
            prepared = staging / "prepared"
            shutil.copytree(matches[0].parent, prepared)
            archived_executable = prepared / spec.archive_executable
            archived_executable.replace(prepared / spec.installed_executable)
            if target.exists():
                raise UserFacingError(
                    ErrorCode.INSTALL_FAILED,
                    "目标工具目录已存在但不完整，请更换补充目录后重试。",
                )
            prepared.replace(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        if on_progress:
            on_progress(100)
        return ToolInstallResult(spec.key, spec.version, executable, {spec.key: executable})

    def _install_winget(
        self,
        spec: ToolInstallSpec,
        cancellation: CancellationToken | None,
        on_progress: Callable[[int], None] | None,
    ) -> ToolInstallResult:
        winget = self.executable_lookup("winget")
        if not winget:
            raise UserFacingError(
                ErrorCode.TOOL_MISSING,
                "未检测到 WinGet，请先从 Microsoft Store 安装“应用安装程序”。",
                retryable=True,
            )
        target = self.install_root / spec.key / "current"
        target.mkdir(parents=True, exist_ok=True)
        download_root = self.install_root / "_downloads"
        download_root.mkdir(parents=True, exist_ok=True)
        if on_progress:
            on_progress(5)
        process_result = self.runner.run(
            CommandRequest(
                winget,
                (
                    "install",
                    "--id",
                    spec.package_id,
                    "--exact",
                    "--source",
                    "winget",
                    "--location",
                    str(target),
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                    "--disable-interactivity",
                ),
                tool_name=spec.display_name,
                timeout_seconds=1800,
                success_codes=(0, 3010),
                environment={"TEMP": str(download_root), "TMP": str(download_root)},
            ),
            cancellation=cancellation,
        )
        tool_paths: dict[str, Path] = {}
        if spec.key == "libreoffice":
            matches = list(target.rglob("soffice.exe"))
            if matches:
                tool_paths["libreoffice"] = matches[0]
        elif spec.key == "ffmpeg":
            for name in ("ffmpeg", "ffprobe"):
                matches = list(target.rglob(f"{name}.exe"))
                if matches:
                    tool_paths[name] = matches[0]
        if on_progress:
            on_progress(100)
        primary = next(iter(tool_paths.values()), None)
        return ToolInstallResult(
            spec.key,
            spec.version,
            primary,
            tool_paths,
            restart_required=process_result.returncode == 3010,
        )
