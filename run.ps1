$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Host "First run: creating a project-local Python environment..."
    python -m venv (Join-Path $ProjectRoot ".venv")
}

& $PythonExe -c "import PySide6, markitdown, rapidocr, onnxruntime, pypdfium2, packaging, pytest, PyInstaller, ai_material_preprocessor" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "First run: installing desktop dependencies..."
    Push-Location $ProjectRoot
    try {
        & $PythonExe -m pip install -e ".[dev,build]"
    }
    finally {
        Pop-Location
    }
}

& $PythonExe -m ai_material_preprocessor
