from __future__ import annotations

from pathlib import Path

from ai_material_preprocessor import __version__
from ai_material_preprocessor.services.release_metadata import validate_release_metadata

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_is_consistent_for_2_0_rc() -> None:
    result = validate_release_metadata(PROJECT_ROOT)

    assert result.version == "2.0.0rc1"
    assert __version__ == result.version
    assert result.errors == ()


def test_release_pipeline_defines_portable_installer_checksums_and_smoke() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    package_script = (PROJECT_ROOT / "scripts" / "package_release.ps1").read_text(encoding="utf-8")
    installer = (PROJECT_ROOT / "installer" / "ai-material-preprocessor.nsi").read_text(
        encoding="utf-8"
    )

    assert "build_release.ps1" in workflow
    assert "verify_installer.ps1" in workflow
    assert "upload-artifact" in workflow
    assert "SHA256SUMS.txt" in package_script
    assert "windows-x64.zip" in package_script
    assert "windows-x64-setup.exe" in installer
    assert "RequestExecutionLevel user" in installer
    assert "AI 素材预处理工具" in installer
    assert "绱犳" not in installer


def test_nsis_bootstrap_extracts_verified_tools_without_installing() -> None:
    bootstrap = (PROJECT_ROOT / "scripts" / "bootstrap_nsis.ps1").read_text(encoding="utf-8-sig")

    assert "Start-Process" not in bootstrap
    assert "--http1.1" in bootstrap
    assert "--noproxy" in bootstrap
    assert '"*"' in bootstrap
    assert "7zr-26.02.exe" in bootstrap
    assert "56B8CC9F4971CEF253644FAFE54063ED7FDCA551D4DEE0F8C6BAA81B855ACD72" in bootstrap
    assert "6745FA76DC2EA031596D8678F6F6B99C3C1B435B4164A63485ADBBC7B8D82EF0" in bootstrap
    assert '& $sevenZip x -y "-o$installRoot" $installer' in bootstrap


def test_release_build_keeps_pytest_temp_data_in_project_work_directory() -> None:
    build_script = (PROJECT_ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8-sig")

    assert 'Join-Path $ProjectRoot "work"' in build_script
    assert "pytest-release-" in build_script
    assert "$env:TEMP = $testTemp" in build_script
    assert "$env:TMP = $testTemp" in build_script
    assert "Remove-Item -LiteralPath $testTemp -Recurse -Force" in build_script


def test_installer_smoke_uses_nsis_destination_as_last_unquoted_argument() -> None:
    verify_script = (PROJECT_ROOT / "scripts" / "verify_installer.ps1").read_text(
        encoding="utf-8-sig"
    )

    assert '$installArguments = @("/S", "/D=$installRoot")' in verify_script
    assert "ArgumentList $installArguments" in verify_script
    assert '/D=`"$installRoot`"' not in verify_script
    assert "if ([string]::IsNullOrWhiteSpace($ProjectRoot))" in verify_script


def test_portable_release_is_extracted_and_started_from_the_zip() -> None:
    verify_script = (PROJECT_ROOT / "scripts" / "verify_release.ps1").read_text(
        encoding="utf-8-sig"
    )
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "Expand-Archive" in verify_script
    assert "portable-smoke-" in verify_script
    assert '"--self-test"' in verify_script
    assert "verify_release.ps1 -ProjectRoot" in workflow
    assert "-Version $env:RELEASE_VERSION" in workflow


def test_release_scripts_support_clean_ci_python_without_project_venv() -> None:
    resolver = (PROJECT_ROOT / "scripts" / "python_runtime.ps1").read_text(encoding="utf-8-sig")
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "Get-Command python" in resolver
    for relative in (
        "scripts/check_quality.ps1",
        "scripts/build_release.ps1",
        "scripts/package_release.ps1",
    ):
        script = (PROJECT_ROOT / relative).read_text(encoding="utf-8-sig")
        assert "[string]$PythonExecutable" in script
        assert "Resolve-PythonExecutable" in script
    assert "-PythonExecutable $python" in workflow


def test_quality_gate_keeps_pytest_temp_data_in_project_work_directory() -> None:
    quality_script = (PROJECT_ROOT / "scripts" / "check_quality.ps1").read_text(
        encoding="utf-8-sig"
    )

    assert "pytest-quality-" in quality_script
    assert "$env:TEMP = $testTemp" in quality_script
    assert "$env:TMP = $testTemp" in quality_script
    assert "Remove-Item -LiteralPath $testTemp -Recurse -Force" in quality_script


def test_ffmpeg_source_download_avoids_unstable_proxy_tls() -> None:
    package_script = (PROJECT_ROOT / "scripts" / "package_release.ps1").read_text(
        encoding="utf-8-sig"
    )

    assert "--http1.1" in package_script
    assert "--noproxy" in package_script
    assert '"*"' in package_script


def test_release_metadata_omits_empty_tag_argument_on_pull_requests() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert '$arguments = @("scripts/check_release_metadata.py"' in workflow
    assert '$arguments += @("--tag", $env:GITHUB_REF_NAME)' in workflow
    assert "--tag $tag" not in workflow


def test_release_documentation_and_github_templates_exist() -> None:
    required = (
        "PRIVACY.md",
        "CONTRIBUTING.md",
        "docs/TROUBLESHOOTING.md",
        "docs/releases/v2.0.0rc1.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/pull_request_template.md",
    )

    assert all((PROJECT_ROOT / relative).is_file() for relative in required)
