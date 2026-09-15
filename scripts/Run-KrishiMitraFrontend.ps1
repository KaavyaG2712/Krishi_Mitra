[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$RepositoryRoot
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
    Write-Host "Starting KrishiMitra web app at http://localhost:5173" -ForegroundColor Cyan
    # Calling `npm run ... -- --host 127.0.0.1` through Windows PowerShell can
    # strip the option names and make Vite treat `127.0.0.1` as its root folder.
    # Invoke the checked-in Vite shim directly so its CLI flags arrive intact.
    & $viteExecutable "--host=127.0.0.1" "--port=5173" "--strictPort"

    if ($LASTEXITCODE -ne 0) {
        throw "The frontend server exited with code $LASTEXITCODE."
    }
}
catch {
    Write-Host "Frontend server could not start: $($_.Exception.Message)" -ForegroundColor Red
}
