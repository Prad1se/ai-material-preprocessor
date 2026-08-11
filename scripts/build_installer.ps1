param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
$releaseDirectory = Join-Path $ProjectRoot "dist\AI-Material-Preprocessor"
if (-not (Test-Path -LiteralPath $releaseDirectory)) {
    throw "Release directory not found. Run scripts\build_release.ps1 first."
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$compiler = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (
    Join-Path $ProjectRoot "scripts\bootstrap_nsis.ps1"
) -ProjectRoot $ProjectRoot | Select-Object -Last 1
if (-not (Test-Path -LiteralPath $compiler)) { throw "NSIS compiler was not prepared." }

$script = Join-Path $ProjectRoot "installer\ai-material-preprocessor.nsi"
& $compiler /V2 "/DAPP_VERSION=$Version" "/DPROJECT_ROOT=$ProjectRoot" `
    "/DRELEASE_DIR=$releaseDirectory" "/DOUTPUT_DIR=$OutputDirectory" $script
if ($LASTEXITCODE -ne 0) { throw "NSIS installer build failed." }

$installer = Join-Path $OutputDirectory "AI-Material-Preprocessor-v$Version-windows-x64-setup.exe"
if (-not (Test-Path -LiteralPath $installer)) { throw "Expected installer was not created." }
Write-Output $installer
