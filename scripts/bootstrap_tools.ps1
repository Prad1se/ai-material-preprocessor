param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$IncludeExifTool
)

$ErrorActionPreference = "Stop"
$toolsRoot = Join-Path $ProjectRoot "tools"
$downloadRoot = Join-Path $toolsRoot "_downloads"
New-Item -ItemType Directory -Force -Path $toolsRoot, $downloadRoot | Out-Null

function Invoke-Download([string]$Url, [string]$Output) {
    & curl.exe --fail --location --retry 3 --output $Output $Url
    if ($LASTEXITCODE -ne 0) { throw "Download failed: $Url" }
}

function Install-FFmpeg {
    $target = Join-Path $toolsRoot "ffmpeg\bin\ffmpeg.exe"
    $probeTarget = Join-Path $toolsRoot "ffmpeg\bin\ffprobe.exe"
    if ((Test-Path -LiteralPath $target) -and (Test-Path -LiteralPath $probeTarget)) {
        Write-Host "FFmpeg and ffprobe already exist; skipping download."
        return
    }
    $python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { throw "Project Python environment not found." }
    $resolvedLines = & $python -c "from static_ffmpeg import run; print('|'.join(run.get_or_fetch_platform_executables_else_raise()))"
    $resolved = ($resolvedLines | Select-Object -Last 1).Trim()
    $paths = $resolved -split '\|'
    if ($paths.Count -ne 2 -or -not (Test-Path -LiteralPath $paths[0]) -or -not (Test-Path -LiteralPath $paths[1])) {
        throw "static-ffmpeg did not provide ffmpeg.exe and ffprobe.exe."
    }
    $targetBin = Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $targetBin | Out-Null
    Copy-Item -LiteralPath $paths[0] -Destination $target -Force
    Copy-Item -LiteralPath $paths[1] -Destination $probeTarget -Force
    Write-Host "FFmpeg and ffprobe installed."
}

function Install-ExifTool {
    $target = Join-Path $toolsRoot "exiftool\exiftool.exe"
    if (Test-Path -LiteralPath $target) {
        Write-Host "ExifTool already exists; skipping download."
        return
    }

    $archive = Join-Path $downloadRoot "exiftool-13.59_64.zip"
    Invoke-Download "https://sourceforge.net/projects/exiftool/files/exiftool-13.59_64.zip/download" $archive
    $temporary = Join-Path ([IO.Path]::GetTempPath()) ("ai-material-exiftool-" + [guid]::NewGuid())
    try {
        Expand-Archive -LiteralPath $archive -DestinationPath $temporary
        $executable = Get-ChildItem -Path $temporary -Recurse -Filter "exiftool(-k).exe" | Select-Object -First 1
        if ($null -eq $executable) { throw "ExifTool executable was not found in the archive." }
        $sourceFolder = $executable.Directory.FullName
        $targetFolder = Split-Path -Parent $target
        New-Item -ItemType Directory -Force -Path $targetFolder | Out-Null
        Get-ChildItem -LiteralPath $sourceFolder -Force | Copy-Item -Destination $targetFolder -Recurse
        Move-Item -LiteralPath (Join-Path $targetFolder "exiftool(-k).exe") -Destination $target
    }
    finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
    }
    Write-Host "ExifTool installed."
}

Install-FFmpeg
if ($IncludeExifTool) { Install-ExifTool }
