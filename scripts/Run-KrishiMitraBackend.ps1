[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$RepositoryRoot,
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

try {
    $backendDirectory = Join-Path $RepositoryRoot "backend"
    $pythonExecutable = Join-Path $backendDirectory ".venv\Scripts\python.exe"

    if (-not (Test-Path -LiteralPath $pythonExecutable)) {
        throw "Backend virtual environment is missing: $pythonExecutable"
    }

    Set-Location $backendDirectory
    Write-Host "Starting KrishiMitra API at http://127.0.0.1:$Port" -ForegroundColor Cyan
    Write-Host "API documentation: http://127.0.0.1:$Port/docs" -ForegroundColor Cyan
    & $pythonExecutable -m uvicorn app.main:app --reload --port $Port

    if ($LASTEXITCODE -ne 0) {
        throw "The backend server exited with code $LASTEXITCODE."
    }
}
catch {
    Write-Host "Backend server could not start: $($_.Exception.Message)" -ForegroundColor Red
}
