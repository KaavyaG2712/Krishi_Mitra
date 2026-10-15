[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$RepositoryRoot,
    [ValidateRange(1, 65535)]
    [int]$Port = 5173,
    [string]$ApiBaseUrl = "http://127.0.0.1:8000/api/v1"
)

$ErrorActionPreference = "Stop"

try {
    $frontendDirectory = Join-Path $RepositoryRoot "frontend"
    $npmCommand = Get-Command npm -ErrorAction Stop

    $viteExecutable = Join-Path $frontendDirectory "node_modules\.bin\vite.cmd"
    if (-not (Test-Path -LiteralPath $viteExecutable)) {
        throw "Frontend packages are missing. Run scripts/Start-KrishiMitra.ps1 -InstallMissing first."
    }

    Set-Location $frontendDirectory
    Write-Host "Starting KrishiMitra web app at http://localhost:$Port" -ForegroundColor Cyan
    # Calling `npm run ... -- --host 127.0.0.1` through Windows PowerShell can
    # strip the option names and make Vite treat `127.0.0.1` as its root folder.
    # Invoke the checked-in Vite shim directly so its CLI flags arrive intact.
    $env:VITE_API_BASE_URL = $ApiBaseUrl
    & $viteExecutable "--host=127.0.0.1" "--port=$Port" "--strictPort"

    if ($LASTEXITCODE -ne 0) {
        throw "The frontend server exited with code $LASTEXITCODE."
    }
}
catch {
    Write-Host "Frontend server could not start: $($_.Exception.Message)" -ForegroundColor Red
}
