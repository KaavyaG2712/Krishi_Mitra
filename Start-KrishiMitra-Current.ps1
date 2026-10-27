[CmdletBinding()]
param(
    [switch]$InstallMissing,
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 5173
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Status {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "[KrishiMitra current] $Message" -ForegroundColor Cyan
}

function Test-HttpEndpoint {
    param([Parameter(Mandatory)][string]$Uri)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    }
    catch { return $false }
}

function Wait-HttpEndpoint {
    param([Parameter(Mandatory)][string]$Uri, [int]$TimeoutSeconds = 30)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-HttpEndpoint -Uri $Uri) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Stop-OldKrishiMitraProcess {
    param([Parameter(Mandatory)][int]$Port)
    $connections = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    $processTable = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    foreach ($connection in $connections) {
        $processId = [int]$connection.OwningProcess
        if ($processId -eq $PID) { continue }
        $processInfo = $processTable | Where-Object { $_.ProcessId -eq $processId } | Select-Object -First 1
        $commandLine = if ($null -eq $processInfo) { "" } else { [string]$processInfo.CommandLine }
        # Uvicorn's reload parent can exit while its multiprocessing server
        # child still owns the socket. Include those orphaned children when
        # deciding which stale listener belongs to this application.
        $children = @($processTable | Where-Object { $_.ParentProcessId -eq $processId })
        $childIsUvicorn = @($children | Where-Object {
            ([string]$_.CommandLine -match "multiprocessing\.spawn_main") -and ([string]$_.Name -match "python")
        }).Count -gt 0
        $isKrishiMitra = ($commandLine -match "uvicorn\s+app\.main:app") -or
            (($commandLine -match "vite") -and ($commandLine -match "--port[=\s]+5173")) -or
            $childIsUvicorn
        if ($isKrishiMitra) {
            Write-Status "Stopping old KrishiMitra process $processId on port $Port."
            & taskkill.exe /PID $processId /T /F *> $null
            foreach ($child in $children) {
                & taskkill.exe /PID ([int]$child.ProcessId) /T /F *> $null
            }
        }
        elseif ($null -ne $processInfo) {
            throw "Port $Port is being used by another application. Stop that application before starting KrishiMitra."
        }
    }
}

function Start-ServiceProcess {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$RunnerPath,
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][string]$PowerShellExecutable,
        [Parameter(Mandatory)][string]$LogDirectory,
        [string[]]$RunnerArguments = @()
    )
    $outLog = Join-Path $LogDirectory "$Name.out.log"
    $errLog = Join-Path $LogDirectory "$Name.err.log"
    $arguments = @("-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $RunnerPath, "-RepositoryRoot", $RepositoryRoot) + $RunnerArguments
    Start-Process -FilePath $PowerShellExecutable -WorkingDirectory $WorkingDirectory -WindowStyle Hidden `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog -ArgumentList $arguments | Out-Null
    Write-Status "$Name started. Logs: $outLog and $errLog"
}

function Ensure-CropHealthRuntime {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$BackendDirectory,
        [Parameter(Mandatory)][string]$BackendPython,
        [switch]$InstallMissing
    )

    $checkpoint = Join-Path $RepositoryRoot "models\checkpoints\mobilenetv2-10class-v1\best_model.pt"
    if (-not (Test-Path -LiteralPath $checkpoint)) {
        $git = Get-Command git -ErrorAction SilentlyContinue
        $candidateRoots = @()
        if ($null -ne $git) {
            $worktreeLines = @(& $git.Source -C $RepositoryRoot worktree list --porcelain 2>$null)
            foreach ($line in $worktreeLines) {
                if ($line -match '^worktree\s+(.+)$') { $candidateRoots += $Matches[1].Trim() }
            }
        }
        foreach ($candidateRoot in ($candidateRoots | Select-Object -Unique)) {
            $candidate = Join-Path $candidateRoot "models\checkpoints\mobilenetv2-10class-v1"
            if ((Test-Path -LiteralPath (Join-Path $candidate "best_model.pt")) -and ($candidate -ne (Split-Path $checkpoint))) {
                Write-Status "Restoring the crop-health checkpoint from $candidate."
                New-Item -ItemType Directory -Path (Split-Path $checkpoint) -Force | Out-Null
                Copy-Item -LiteralPath $candidate -Destination (Split-Path $checkpoint) -Recurse -Force
                break
            }
        }
    }
    if (-not (Test-Path -LiteralPath $checkpoint)) {
        throw "The crop-health checkpoint is missing. Keep models/checkpoints/mobilenetv2-10class-v1 in a project worktree, or run the model training pipeline first."
    }

    # On Windows PowerShell, native stderr can become a terminating error when
    # ErrorActionPreference is Stop. A missing torch install is expected on a
    # fresh checkout, so capture that probe without aborting setup.
    $savedErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $mlImport = & $BackendPython -c "import torch, torchvision" 2>&1
        $mlImportExitCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $savedErrorPreference }

    if ($mlImportExitCode -ne 0) {
        Write-Status "Installing the crop-health ML runtime (torch and torchvision)."
        Push-Location $BackendDirectory
        try {
            $savedErrorPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                & $BackendPython -m pip install -e ".[ml]"
                $mlInstallExitCode = $LASTEXITCODE
            }
            finally { $ErrorActionPreference = $savedErrorPreference }
        }
        finally { Pop-Location }
        if ($mlInstallExitCode -ne 0) {
            throw "The crop-health ML runtime could not be installed (pip exit code $mlInstallExitCode). Import check: $mlImport"
        }

        $savedErrorPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $mlVerify = & $BackendPython -c "import torch, torchvision; print(torch.__version__, torchvision.__version__)" 2>&1
            $mlVerifyExitCode = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $savedErrorPreference }
        if ($mlVerifyExitCode -ne 0) {
            throw "The crop-health ML runtime did not import after installation: $mlVerify"
        }
        Write-Status "Crop-health ML runtime is ready: $mlVerify"
    }
}

try {
    $repositoryRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
    $backendDirectory = Join-Path $repositoryRoot "backend"
    $frontendDirectory = Join-Path $repositoryRoot "frontend"
    $backendPython = Join-Path $backendDirectory ".venv\Scripts\python.exe"
    $backendEnvironment = Join-Path $backendDirectory ".env"
    $backendEnvironmentExample = Join-Path $backendDirectory ".env.example"
    $frontendVite = Join-Path $frontendDirectory "node_modules\.bin\vite.cmd"
    $backendRunner = Join-Path $repositoryRoot "scripts\Run-KrishiMitraBackend.ps1"
    $frontendRunner = Join-Path $repositoryRoot "scripts\Run-KrishiMitraFrontend.ps1"
    $logDirectory = Join-Path $repositoryRoot ".codex-finalizer\logs"
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

    Write-Status "Using this checkout: $repositoryRoot"
    foreach ($requiredPath in @($backendDirectory, $frontendDirectory, $backendEnvironmentExample, $backendRunner, $frontendRunner)) {
        if (-not (Test-Path -LiteralPath $requiredPath)) { throw "Required project file or folder is missing: $requiredPath" }
    }
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($null -eq $docker) { throw "Docker Desktop is required but the docker command was not found." }
    if ($null -eq $npm) { throw "Node.js LTS is required but the npm command was not found." }

    if (-not (Test-Path -LiteralPath $backendPython)) {
        if (-not $InstallMissing) { throw "Backend environment is missing. Run Start-KrishiMitra.cmd to install missing packages." }
        $py = Get-Command py -ErrorAction SilentlyContinue
        if ($null -eq $py) { throw "Python Launcher (py) was not found." }
        Write-Status "Creating the backend virtual environment."
        Push-Location $backendDirectory
        try { & $py.Source -3.12 -m venv .venv }
        finally { Pop-Location }
    }
    if (-not (Test-Path -LiteralPath $backendPython)) { throw "Backend Python was not created at $backendPython." }

    if (-not (Test-Path -LiteralPath $frontendVite)) {
        if (-not $InstallMissing) { throw "Frontend packages are missing. Run Start-KrishiMitra.cmd to install missing packages." }
        Write-Status "Installing frontend packages from package-lock.json."
        Push-Location $frontendDirectory
        try { & $npm.Source ci }
        finally { Pop-Location }
    }
    if (-not (Test-Path -LiteralPath $frontendVite)) { throw "Frontend Vite was not installed at $frontendVite." }

    if (-not (Test-Path -LiteralPath $backendEnvironment)) {
        Copy-Item -LiteralPath $backendEnvironmentExample -Destination $backendEnvironment
        Write-Status "Created backend/.env from backend/.env.example. Local chat needs no API key; Gemini is optional for translation and server speech."
    }

    Ensure-CropHealthRuntime -RepositoryRoot $repositoryRoot -BackendDirectory $backendDirectory `
        -BackendPython $backendPython -InstallMissing:$InstallMissing

    Write-Status "Stopping stale KrishiMitra servers from other worktrees."
    Stop-OldKrishiMitraProcess -Port $FrontendPort
    Stop-OldKrishiMitraProcess -Port $BackendPort
    Start-Sleep -Milliseconds 700

    # A crashed/restarted Windows process can leave a stale listener entry for
    # a short time. Use the next local port in that case so the current
    # checkout still starts cleanly and the frontend points to the same API.
    if (@(Get-NetTCPConnection -State Listen -LocalPort $BackendPort -ErrorAction SilentlyContinue).Count -gt 0) {
        $fallbackPort = if ($BackendPort -eq 8000) { 8001 } else { $BackendPort + 1 }
        Stop-OldKrishiMitraProcess -Port $fallbackPort
        Start-Sleep -Milliseconds 500
        if (@(Get-NetTCPConnection -State Listen -LocalPort $fallbackPort -ErrorAction SilentlyContinue).Count -gt 0) {
            throw "Backend port $BackendPort is still occupied and fallback port $fallbackPort is also unavailable."
        }
        Write-Status "Port $BackendPort is still occupied by an old listener; using backend port $fallbackPort for this launch."
        $BackendPort = $fallbackPort
    }

    Push-Location $repositoryRoot
    try {
        Write-Status "Starting PostgreSQL + pgvector."
        & $docker.Source compose up -d db
        if ($LASTEXITCODE -ne 0) { throw "Docker database startup failed." }
        $databaseDeadline = [DateTime]::UtcNow.AddSeconds(60)
        while ([DateTime]::UtcNow -lt $databaseDeadline) {
            & $docker.Source compose exec -T db pg_isready -q -U krishimitra -d krishimitra *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Seconds 2
        }
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL did not become ready within 60 seconds." }
        # Alembic creates alembic_version on the first upgrade. Do not query
        # that table before the initial migration: a fresh database has no
        # such relation yet. `upgrade head` is idempotent, so it is safe to
        # run at every startup and also upgrades databases after code updates.
        Write-Status "Applying database migrations to the latest version."
        Push-Location $backendDirectory
        try {
            $savedErrorPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                & $backendPython -m alembic upgrade head
                $migrationExitCode = $LASTEXITCODE
                if ($migrationExitCode -eq 0) {
                    Write-Status "Loading the local agronomy knowledge library."
                    & $backendPython -m app.modules.advisor.seed_knowledge
                    $seedExitCode = $LASTEXITCODE
                }
            }
            finally { $ErrorActionPreference = $savedErrorPreference }
        }
        finally { Pop-Location }
        if ($migrationExitCode -ne 0) { throw "Database migrations failed." }
        if ($seedExitCode -ne 0) { throw "The local agronomy knowledge library could not be loaded." }
    }
    finally { Pop-Location }

    $windowsPowerShell = Get-Command powershell.exe -ErrorAction Stop
    Start-ServiceProcess -Name "Backend-current" -RunnerPath $backendRunner -RepositoryRoot $repositoryRoot `
        -WorkingDirectory $backendDirectory -PowerShellExecutable $windowsPowerShell.Source -LogDirectory $logDirectory `
        -RunnerArguments @("-Port", $BackendPort)
    if (-not (Wait-HttpEndpoint -Uri "http://127.0.0.1:$BackendPort/api/v1/health" -TimeoutSeconds 30)) {
        throw "The current backend did not become ready. Read .codex-finalizer\logs\Backend-current.err.log."
    }
    Start-ServiceProcess -Name "Frontend-current" -RunnerPath $frontendRunner -RepositoryRoot $repositoryRoot `
        -WorkingDirectory $frontendDirectory -PowerShellExecutable $windowsPowerShell.Source -LogDirectory $logDirectory `
        -RunnerArguments @("-Port", $FrontendPort, "-ApiBaseUrl", "http://127.0.0.1:$BackendPort/api/v1")
    if (-not (Wait-HttpEndpoint -Uri "http://127.0.0.1:$FrontendPort/" -TimeoutSeconds 30)) {
        throw "The current frontend did not become ready. Read .codex-finalizer\logs\Frontend-current.err.log."
    }

    Write-Host ""
    Write-Host "KrishiMitra current checkout is ready:" -ForegroundColor Green
    Write-Host "  Website: http://127.0.0.1:$FrontendPort"
    Write-Host "  API docs: http://127.0.0.1:$BackendPort/docs"
    Write-Host "  Modules: Crop Health, Soil & Crop Planning, Local Agronomy Knowledge Chat"
    Write-Host "  Logs: $logDirectory"
    Start-Process "http://127.0.0.1:$FrontendPort/"
}
catch {
    Write-Host ""
    Write-Host "KrishiMitra current launch failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
