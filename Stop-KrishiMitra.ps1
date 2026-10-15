[CmdletBinding()]
param(
    [switch]$KeepDatabase
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$backendRunner = (Join-Path $projectRoot 'scripts\Run-KrishiMitraBackend.ps1').ToLowerInvariant()
$frontendRunner = (Join-Path $projectRoot 'scripts\Run-KrishiMitraFrontend.ps1').ToLowerInvariant()
$backendPython = (Join-Path $projectRoot 'backend\.venv\Scripts\python.exe').ToLowerInvariant()
$viteEntry = (Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js').ToLowerInvariant()
$processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
$managedIds = [Collections.Generic.HashSet[int]]::new()

foreach ($process in $processes) {
    $commandLine = ([string]$process.CommandLine).Replace('/', '\').ToLowerInvariant()
    $isBackend = $commandLine.Contains($backendRunner) -or
        ($commandLine.Contains($backendPython) -and $commandLine.Contains('uvicorn app.main:app'))
    $isFrontend = $commandLine.Contains($frontendRunner) -or $commandLine.Contains($viteEntry)
    if ($isBackend -or $isFrontend) { [void]$managedIds.Add([int]$process.ProcessId) }
}

foreach ($processId in $managedIds) {
    Write-Host "Stopping KrishiMitra process $processId" -ForegroundColor Cyan
    & taskkill.exe /PID $processId /T /F 2>$null | Out-Null
}

Start-Sleep -Milliseconds 700
$knownPorts = @(8000, 8001, 5173)
$leftoverPorts = @($knownPorts | Where-Object {
    @(Get-NetTCPConnection -State Listen -LocalPort $_ -ErrorAction SilentlyContinue).Count -gt 0
})
if ($leftoverPorts.Count -gt 0) {
    Write-Warning "A process is still listening on port(s) $($leftoverPorts -join ', '). It may belong to another checkout; it was left untouched."
}

if (-not $KeepDatabase) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($null -ne $docker) {
        Push-Location $projectRoot
        try {
            & $docker.Source compose down
            if ($LASTEXITCODE -ne 0) { throw 'Docker Compose could not stop the KrishiMitra database.' }
        }
        finally { Pop-Location }
    }
    else {
        Write-Host 'Docker was not found; no database container was stopped.' -ForegroundColor Yellow
    }
}
else {
    Write-Host 'Database left running by request.' -ForegroundColor Yellow
}

Write-Host 'KrishiMitra frontend and backend are stopped.' -ForegroundColor Green
