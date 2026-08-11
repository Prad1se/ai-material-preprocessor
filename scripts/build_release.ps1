param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "python_runtime.ps1")
$python = Resolve-PythonExecutable -ProjectRoot $ProjectRoot -Preferred $PythonExecutable

$workRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "work"))
$testTemp = Join-Path $workRoot ("pytest-release-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $testTemp | Out-Null
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$env:TEMP = $testTemp
$env:TMP = $testTemp

Push-Location $ProjectRoot
try {
    & $python (Join-Path $ProjectRoot "scripts\check_release_metadata.py")
    if ($LASTEXITCODE -ne 0) { throw "Release metadata check failed." }

    & $python -m pytest -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw "Tests failed; release build stopped." }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\bootstrap_tools.ps1") -ProjectRoot $ProjectRoot -PythonExecutable $python
    if ($LASTEXITCODE -ne 0) { throw "Portable FFmpeg setup failed." }

    & $python -m PyInstaller --noconfirm --clean "app.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    $release = Join-Path $ProjectRoot "dist\AI-Material-Preprocessor"
    foreach ($document in @(
        "config.json",
        "README.md",
        "ROADMAP.md",
        "CHANGELOG.md",
        "LICENSE",
        "PRIVACY.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "THIRD_PARTY_NOTICES.md"
    )) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $document) -Destination $release -Force
    }
    $docs = Join-Path $release "docs"
    New-Item -ItemType Directory -Force -Path $docs | Out-Null
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "docs\TROUBLESHOOTING.md") -Destination $docs -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "docs\releases\v2.0.0rc1.md") -Destination $docs -Force
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
    if ($null -eq $previousTemp) { Remove-Item Env:TEMP -ErrorAction SilentlyContinue }
    else { $env:TEMP = $previousTemp }
    if ($null -eq $previousTmp) { Remove-Item Env:TMP -ErrorAction SilentlyContinue }
    else { $env:TMP = $previousTmp }

    $resolvedTestTemp = [IO.Path]::GetFullPath($testTemp)
    $workPrefix = $workRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if ($resolvedTestTemp.StartsWith($workPrefix, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $testTemp)) {
        Remove-Item -LiteralPath $testTemp -Recurse -Force
    }
}
