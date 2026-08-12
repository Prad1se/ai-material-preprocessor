from __future__ import annotations

import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import pytest

from ai_material_preprocessor.errors import ErrorCode, UserFacingError
from ai_material_preprocessor.infrastructure.processes import CancellationToken, CommandResult
from ai_material_preprocessor.services.tool_installer import (
    InstallMethod,
    ToolInstaller,
    ToolInstallResult,
    ToolInstallSpec,
    default_tool_install_root,
)
from ai_material_preprocessor.ui.tool_installation import apply_install_result


def _archive_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _portable_spec(payload: bytes, *, digest: str | None = None) -> ToolInstallSpec:
    return ToolInstallSpec(
        key="exiftool",
        display_name="ExifTool",
        method=InstallMethod.PORTABLE_ARCHIVE,
        version="13.59",
        description="读取视频拍摄时间、GPS 和设备信息。",
        source_url="https://downloads.example.test/exiftool.zip",
        license_name="Artistic License / GPL",
        license_url="https://exiftool.org/",
        sha256=digest or hashlib.sha256(payload).hexdigest(),
        archive_executable="exiftool(-k).exe",
        installed_executable="exiftool.exe",
    )


def test_default_tool_install_root_uses_local_application_data() -> None:
    result = default_tool_install_root({"LOCALAPPDATA": "D:/用户 数据"})

    assert result == Path("D:/用户 数据/AI Material Preprocessor/tools")


def test_pre_cancelled_install_never_downloads(tmp_path: Path) -> None:
    payload = _archive_bytes({"exiftool-13.59_64/exiftool(-k).exe": b"exe"})
    token = CancellationToken()
    token.cancel()
    downloaded = False

    def download(_url: str, _destination: Path, **_kwargs) -> None:
        nonlocal downloaded
        downloaded = True

    installer = ToolInstaller(
        install_root=tmp_path,
        specs={"exiftool": _portable_spec(payload)},
        downloader=download,
    )

    with pytest.raises(UserFacingError) as captured:
        installer.install("exiftool", cancellation=token)

    assert captured.value.code is ErrorCode.CANCELLED
    assert downloaded is False


def test_portable_install_verifies_extracts_and_keeps_runtime_folder(tmp_path: Path) -> None:
    payload = _archive_bytes(
        {
            "exiftool-13.59_64/exiftool(-k).exe": b"exe",
            "exiftool-13.59_64/exiftool_files/runtime.dll": b"runtime",
        }
    )
    downloads: list[tuple[str, Path]] = []

    def download(url: str, destination: Path, **_kwargs) -> None:
        downloads.append((url, destination))
        destination.write_bytes(payload)

    installer = ToolInstaller(
        install_root=tmp_path / "应用 工具",
        specs={"exiftool": _portable_spec(payload)},
        downloader=download,
    )

    result = installer.install("exiftool")

    assert downloads[0][0].startswith("https://")
    assert result.executable_path == (
        tmp_path / "应用 工具" / "exiftool" / "13.59" / "exiftool.exe"
    )
    assert result.executable_path.read_bytes() == b"exe"
    assert (result.executable_path.parent / "exiftool_files" / "runtime.dll").read_bytes() == (
        b"runtime"
    )


def test_hash_mismatch_removes_partial_install_and_preserves_other_version(
    tmp_path: Path,
) -> None:
    payload = _archive_bytes({"exiftool-13.59_64/exiftool(-k).exe": b"tampered"})
    install_root = tmp_path / "tools"
    previous = install_root / "exiftool" / "13.58" / "exiftool.exe"
    previous.parent.mkdir(parents=True)
    previous.write_bytes(b"working")

    def download(_url: str, destination: Path, **_kwargs) -> None:
        destination.write_bytes(payload)

    installer = ToolInstaller(
        install_root=install_root,
        specs={"exiftool": _portable_spec(payload, digest="0" * 64)},
        downloader=download,
    )

    with pytest.raises(UserFacingError) as captured:
        installer.install("exiftool")

    assert captured.value.code is ErrorCode.INTEGRITY_FAILED
    assert previous.read_bytes() == b"working"
    assert not (install_root / "exiftool" / "13.59").exists()


def test_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    payload = _archive_bytes(
        {
            "exiftool-13.59_64/exiftool(-k).exe": b"exe",
            "../escaped.txt": b"must not escape",
        }
    )

    def download(_url: str, destination: Path, **_kwargs) -> None:
        destination.write_bytes(payload)

    installer = ToolInstaller(
        install_root=tmp_path / "tools",
        specs={"exiftool": _portable_spec(payload)},
        downloader=download,
    )

    with pytest.raises(UserFacingError) as captured:
        installer.install("exiftool")

    assert captured.value.code is ErrorCode.INTEGRITY_FAILED
    assert not (tmp_path / "escaped.txt").exists()


def test_libreoffice_install_uses_exact_winget_package_without_shell(tmp_path: Path) -> None:
    requests = []

    class Runner:
        def run(self, request, **_kwargs):
            requests.append(request)
            return CommandResult(request.command, 0, "installed", "", 1.0)

    spec = ToolInstallSpec(
        key="libreoffice",
        display_name="LibreOffice",
        method=InstallMethod.WINGET,
        version="current",
        description="Word/PPT 转 PDF 的 Office 回退。",
        source_url="https://www.libreoffice.org/download/",
        license_name="MPL-2.0",
        license_url="https://www.libreoffice.org/licenses/",
        package_id="TheDocumentFoundation.LibreOffice",
    )
    installer = ToolInstaller(
        install_root=tmp_path,
        specs={"libreoffice": spec},
        runner=Runner(),
        executable_lookup=lambda name: "C:/Windows/winget.exe" if name == "winget" else None,
    )

    result = installer.install("libreoffice")

    request = requests[0]
    assert request.executable == "C:/Windows/winget.exe"
    assert request.arguments == (
        "install",
        "--id",
        "TheDocumentFoundation.LibreOffice",
        "--exact",
        "--source",
        "winget",
        "--location",
        str(tmp_path / "libreoffice" / "current"),
        "--accept-source-agreements",
        "--accept-package-agreements",
        "--disable-interactivity",
    )
    assert request.success_codes == (0, 3010)
    assert request.environment["TEMP"] == str(tmp_path / "_downloads")
    assert request.environment["TMP"] == str(tmp_path / "_downloads")
    assert result.executable_path is None


def test_winget_reboot_required_code_is_reported_to_ui(tmp_path: Path) -> None:
    class Runner:
        def run(self, request, **_kwargs):
            return CommandResult(request.command, 3010, "restart required", "", 1.0)

    spec = ToolInstallSpec(
        key="libreoffice",
        display_name="LibreOffice",
        method=InstallMethod.WINGET,
        version="current",
        description="Office 回退。",
        source_url="https://www.libreoffice.org/download/",
        license_name="MPL-2.0",
        license_url="https://www.libreoffice.org/licenses/",
        package_id="TheDocumentFoundation.LibreOffice",
    )
    installer = ToolInstaller(
        install_root=tmp_path,
        specs={"libreoffice": spec},
        runner=Runner(),
        executable_lookup=lambda _name: "C:/Windows/winget.exe",
    )

    result = installer.install("libreoffice")

    assert result.restart_required is True


def test_missing_winget_has_actionable_error(tmp_path: Path) -> None:
    spec = ToolInstallSpec(
        key="libreoffice",
        display_name="LibreOffice",
        method=InstallMethod.WINGET,
        version="current",
        description="Office 回退。",
        source_url="https://www.libreoffice.org/download/",
        license_name="MPL-2.0",
        license_url="https://www.libreoffice.org/licenses/",
        package_id="TheDocumentFoundation.LibreOffice",
    )
    installer = ToolInstaller(
        install_root=tmp_path,
        specs={"libreoffice": spec},
        executable_lookup=lambda _name: None,
    )

    with pytest.raises(UserFacingError) as captured:
        installer.install("libreoffice")

    assert captured.value.code is ErrorCode.TOOL_MISSING
    assert "WinGet" in captured.value.user_message


def test_install_result_updates_only_managed_tool_paths(tmp_path: Path) -> None:
    executable = tmp_path / "工具" / "exiftool.exe"
    config = {
        "tools": {"exiftool": "", "ffmpeg": "D:/existing/ffmpeg.exe"},
        "tool_management": {"install_directory": str(tmp_path)},
    }
    installed = ToolInstallResult("exiftool", "13.59", executable, {"exiftool": executable})

    updated = apply_install_result(config, installed)

    assert updated["tools"]["exiftool"] == str(executable)
    assert updated["tools"]["ffmpeg"] == "D:/existing/ffmpeg.exe"
    assert config["tools"]["exiftool"] == ""
