param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$exe = Join-Path $ProjectRoot "dist\AI-Material-Preprocessor\AI-Material-Preprocessor.exe"
$output = Join-Path $ProjectRoot "work\packaged-self-test"
if (-not (Test-Path -LiteralPath $exe)) { throw "Release executable not found." }

if (Test-Path -LiteralPath $output) {
    $resolved = (Resolve-Path -LiteralPath $output).Path
    $workRoot = (Join-Path $ProjectRoot "work") + [IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($workRoot)) { throw "Unsafe diagnostics path." }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

$process = Start-Process -FilePath $exe -ArgumentList @("--self-test", $output) -Wait -PassThru
if ($process.ExitCode -ne 0) { throw "Packaged self-test returned $($process.ExitCode)." }
$reportPath = Join-Path $output "diagnostics.json"
if (-not (Test-Path -LiteralPath $reportPath)) { throw "Diagnostics report was not created." }
$report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($report.overall -ne "passed") { throw "Packaged self-test report failed." }
Write-Host "Packaged self-test passed: $reportPath"
