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
    & $python -m ruff format --check src tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff format check failed." }
    & $python -m ruff check src tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff lint failed." }
    & $python -m mypy src
    if ($LASTEXITCODE -ne 0) { throw "mypy failed." }
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
}
finally {
    Pop-Location
}
