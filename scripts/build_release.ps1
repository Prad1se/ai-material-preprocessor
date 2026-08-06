param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Run run.ps1 first to create the project environment."
}

Push-Location $ProjectRoot
try {
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "Tests failed; release build stopped." }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\bootstrap_tools.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Portable FFmpeg setup failed." }

    & $python -m PyInstaller --noconfirm --clean "app.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    $release = Join-Path $ProjectRoot "dist\AI-Material-Preprocessor"
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "config.json") -Destination $release -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $release -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "ROADMAP.md") -Destination $release -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "CHANGELOG.md") -Destination $release -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "LICENSE") -Destination $release -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "THIRD_PARTY_NOTICES.md") -Destination $release -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "third_party_licenses") -Destination $release -Recurse -Force

    $releaseTools = Join-Path $release "tools"
    New-Item -ItemType Directory -Force -Path $releaseTools | Out-Null
    foreach ($toolName in @("ffmpeg", "exiftool")) {
        $toolSource = Join-Path $ProjectRoot "tools\$toolName"
        if (Test-Path -LiteralPath $toolSource) {
            Copy-Item -LiteralPath $toolSource -Destination $releaseTools -Recurse -Force
        }
    }
    Write-Host "Release directory: $release"
}
finally {
    Pop-Location
}
