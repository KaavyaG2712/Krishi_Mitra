[CmdletBinding()]
param(
    [switch]$InstallMissing,
    [switch]$OpenBrowser,
    [ValidateRange(10, 300)]
    [int]$DatabaseTimeoutSeconds = 60
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Status {
    param([Parameter(Mandatory)][string]$Message)

    Write-Host "[KrishiMitra] $Message" -ForegroundColor Cyan
}

function Test-ListeningPort {
    param([Parameter(Mandatory)][int]$Port)

    try {
        return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -First 1)
    }
    catch {
        return $false
    }
}

function Test-BackendDependencies {
    param([Parameter(Mandatory)][string]$PythonExecutable)

    & $PythonExecutable -c "import alembic, fastapi, torch, torchvision, uvicorn" 2>$null
    return $LASTEXITCODE -eq 0
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$Description,
        [Parameter(Mandatory)][scriptblock]$Action
    )

    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed (exit code $LASTEXITCODE)."
    }
}

function Start-ServiceTerminal {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$RunnerPath,
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][string]$PowerShellExecutable
    )

    $escapedRunnerPath = $RunnerPath.Replace("'", "''")
    $escapedRepositoryRoot = $RepositoryRoot.Replace("'", "''")
    $command = "& '$escapedRunnerPath' -RepositoryRoot '$escapedRepositoryRoot'"
    $encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))

    Start-Process -FilePath $PowerShellExecutable `
        -WorkingDirectory $WorkingDirectory `
        -ArgumentList @("-NoExit", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encodedCommand) |
        Out-Null

    Write-Status "$Name terminal opened."
}

try {
    $repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    $backendDirectory = Join-Path $repositoryRoot "backend"
    $frontendDirectory = Join-Path $repositoryRoot "frontend"
    $backendPython = Join-Path $backendDirectory ".venv\Scripts\python.exe"
    $backendEnvironment = Join-Path $backendDirectory ".env"
    $backendEnvironmentExample = Join-Path $backendDirectory ".env.example"
    $frontendNodeModules = Join-Path $frontendDirectory "node_modules"
    $frontendVite = Join-Path $frontendNodeModules ".bin\vite.cmd"
    $modelCheckpoint = Join-Path $repositoryRoot "models\checkpoints\mobilenetv2-10class-v1\best_model.pt"
    $backendRunner = Join-Path $PSScriptRoot "Run-KrishiMitraBackend.ps1"
    $frontendRunner = Join-Path $PSScriptRoot "Run-KrishiMitraFrontend.ps1"

    Write-Status "Checking local prerequisites."

    foreach ($requiredPath in @($backendDirectory, $frontendDirectory, $backendEnvironmentExample, $backendRunner, $frontendRunner)) {
        if (-not (Test-Path -LiteralPath $requiredPath)) {
            throw "Required project file or folder is missing: $requiredPath"
        }
    }

    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    if ($null -eq $dockerCommand) {
        throw "Docker Desktop is required but the 'docker' command was not found. Install and start Docker Desktop, then rerun this launcher."
    }

    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    if ($null -eq $npmCommand) {
        throw "Node.js LTS is required but the 'npm' command was not found. Install Node.js LTS, then rerun this launcher."
    }

    if (-not (Test-Path -LiteralPath $backendPython)) {
        if (-not $InstallMissing) {
            throw "Backend virtual environment is missing. Run .\scripts\Start-KrishiMitra.ps1 -InstallMissing once, then use Start-KrishiMitra.cmd afterwards."
        }

        $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
        if ($null -eq $pythonLauncher) {
            throw "Python Launcher ('py') was not found. Install Python 3.12, then rerun this launcher with -InstallMissing."
        }

        Write-Status "Creating the Python 3.12 virtual environment."
        Push-Location $backendDirectory
        try {
            Invoke-Checked "Creating the backend virtual environment" { & $pythonLauncher.Source -3.12 -m venv .venv }
        }
        finally {
            Pop-Location
        }
    }

    if (-not (Test-Path -LiteralPath $backendPython)) {
        throw "The backend virtual environment was not created at $backendPython."
    }

    if (-not (Test-BackendDependencies -PythonExecutable $backendPython)) {
        if (-not $InstallMissing) {
            throw "Backend Python packages are incomplete. Run .\scripts\Start-KrishiMitra.ps1 -InstallMissing once, then use Start-KrishiMitra.cmd afterwards."
        }

        Write-Status "Installing backend Python packages. This can take several minutes on the first run."
        Push-Location $backendDirectory
        try {
            Invoke-Checked "Installing backend Python packages" { & $backendPython -m pip install -e ".[dev,ml]" }
        }
        finally {
            Pop-Location
        }
    }

    if (-not (Test-BackendDependencies -PythonExecutable $backendPython)) {
        throw "The backend Python environment is still incomplete after setup."
    }

    if (-not ((Test-Path -LiteralPath $frontendNodeModules) -and (Test-Path -LiteralPath $frontendVite))) {
        if (-not $InstallMissing) {
            throw "Frontend dependencies are missing. Run .\scripts\Start-KrishiMitra.ps1 -InstallMissing once, then use Start-KrishiMitra.cmd afterwards."
        }

        Write-Status "Installing frontend packages from package-lock.json."
        Push-Location $frontendDirectory
        try {
            Invoke-Checked "Installing frontend packages" { & $npmCommand.Source ci }
        }
        finally {
            Pop-Location
        }
    }

    if (-not (Test-Path -LiteralPath $backendEnvironment)) {
        Copy-Item -LiteralPath $backendEnvironmentExample -Destination $backendEnvironment
        Write-Status "Created backend/.env from backend/.env.example without overwriting any existing configuration."
    }

    if (-not (Test-Path -LiteralPath $modelCheckpoint)) {
        Write-Warning "The trained model checkpoint is not present at $modelCheckpoint. The servers will start, but crop-image analysis will not work until the model is trained or restored."
    }

    Push-Location $repositoryRoot
    try {
        Write-Status "Starting the PostgreSQL + pgvector database."
        Invoke-Checked "Starting the database" { & docker compose up -d db }

        Write-Status "Waiting for the database to accept connections."
        $deadline = [DateTime]::UtcNow.AddSeconds($DatabaseTimeoutSeconds)
        $databaseReady = $false
        while ([DateTime]::UtcNow -lt $deadline) {
            & docker compose exec -T db pg_isready -q -U krishimitra -d krishimitra *> $null
            if ($LASTEXITCODE -eq 0) {
                $databaseReady = $true
                break
            }
            Start-Sleep -Seconds 2
        }

        if (-not $databaseReady) {
            throw "The database did not become ready within $DatabaseTimeoutSeconds seconds. Run 'docker compose ps' to inspect it."
        }
    }
    finally {
        Pop-Location
    }

    Write-Status "Applying database migrations."
    Push-Location $backendDirectory
    try {
        Invoke-Checked "Applying database migrations" { & $backendPython -m alembic upgrade head }
    }
    finally {
        Pop-Location
    }

    $windowsPowerShell = Get-Command powershell.exe -ErrorAction Stop
    if (Test-ListeningPort -Port 8000) {
        Write-Warning "Port 8000 is already listening. The existing backend was left running."
    }
    else {
        Start-ServiceTerminal -Name "Backend" -RunnerPath $backendRunner -RepositoryRoot $repositoryRoot `
            -WorkingDirectory $backendDirectory -PowerShellExecutable $windowsPowerShell.Source
    }

    if (Test-ListeningPort -Port 5173) {
        Write-Warning "Port 5173 is already listening. The existing frontend was left running."
    }
    else {
        Start-ServiceTerminal -Name "Frontend" -RunnerPath $frontendRunner -RepositoryRoot $repositoryRoot `
            -WorkingDirectory $frontendDirectory -PowerShellExecutable $windowsPowerShell.Source
    }

    Write-Host "" 
    Write-Host "KrishiMitra is ready:" -ForegroundColor Green
    Write-Host "  Website:  http://localhost:5173"
    Write-Host "  API docs: http://127.0.0.1:8000/docs"
    Write-Host "Close the Backend or Frontend terminal to stop that server. Run 'docker compose down' from the repository root to stop the database."

    if ($OpenBrowser) {
        Start-Process "http://localhost:5173"
    }
}
catch {
    Write-Host "" 
    Write-Host "KrishiMitra launch failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
