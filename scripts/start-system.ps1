[CmdletBinding()]
param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$WslUser = "bober",
    [string]$ProjectPath = "/home/bober/projects/graphrag_system",
    [ValidateRange(1, 60)]
    [int]$DelaySeconds = 4,
    [ValidateRange(30, 900)]
    [int]$TimeoutSeconds = 240,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function ConvertTo-BashLiteral {
    param([Parameter(Mandatory)][string]$Value)

    return "'" + $Value.Replace("'", "'`"`"'`"`'") + "'"
}

$quotedProjectPath = ConvertTo-BashLiteral -Value $ProjectPath

function Invoke-WslCommand {
    param(
        [Parameter(Mandatory)][string]$Command,
        [switch]$Capture
    )

    $fullCommand = "cd -- $quotedProjectPath && $Command"
    if ($Capture) {
        $output = & wsl.exe -d $Distro -u $WslUser -- bash -lc $fullCommand 2>&1
        $exitCode = $LASTEXITCODE
        $text = (($output | ForEach-Object { $_.ToString() }) -join "`n").Trim()
        if ($exitCode -ne 0) {
            throw "WSL command failed with exit code $exitCode`: $text"
        }
        return $text
    }

    & wsl.exe -d $Distro -u $WslUser -- bash -lc $fullCommand
    if ($LASTEXITCODE -ne 0) {
        throw "WSL command failed with exit code $LASTEXITCODE`: $Command"
    }
}

function Wait-ForHealthyService {
    param([Parameter(Mandatory)][string]$Service)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $containerId = Invoke-WslCommand -Capture -Command "docker compose ps -q $Service"
        if ($containerId) {
            $status = Invoke-WslCommand -Capture -Command (
                "docker inspect --format " +
                "'{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' " +
                $containerId
            )
            Write-Host "  $Service status: $status"
            if ($status -eq "healthy") {
                return
            }
            if ($status -in @("exited", "dead")) {
                throw "$Service stopped before becoming healthy."
            }
        }
        Start-Sleep -Seconds 2
    }
    throw "Timed out after $TimeoutSeconds seconds waiting for $Service."
}

function Wait-ForRunningService {
    param([Parameter(Mandatory)][string]$Service)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $containerId = Invoke-WslCommand -Capture -Command "docker compose ps -q $Service"
        if ($containerId) {
            $status = Invoke-WslCommand -Capture -Command (
                "docker inspect --format '{{.State.Status}}' $containerId"
            )
            Write-Host "  $Service status: $status"
            if ($status -eq "running") {
                return
            }
            if ($status -in @("exited", "dead")) {
                throw "$Service stopped before reaching running state."
            }
        }
        Start-Sleep -Seconds 2
    }
    throw "Timed out after $TimeoutSeconds seconds waiting for $Service."
}

function Wait-ForCompletedService {
    param([Parameter(Mandatory)][string]$Service)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $containerId = Invoke-WslCommand -Capture -Command "docker compose ps -aq $Service"
        if ($containerId) {
            $state = Invoke-WslCommand -Capture -Command (
                "docker inspect --format '{{.State.Status}}:{{.State.ExitCode}}' $containerId"
            )
            Write-Host "  $Service status: $state"
            if ($state -eq "exited:0") {
                return
            }
            if ($state.StartsWith("exited:") -and $state -ne "exited:0") {
                throw "$Service failed with $state."
            }
        }
        Start-Sleep -Seconds 2
    }
    throw "Timed out after $TimeoutSeconds seconds waiting for $Service."
}

function Wait-ForNativeRuntime {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $apiHealthy = Invoke-WslCommand -Capture -Command (
            "curl -fsS --max-time 3 http://127.0.0.1:8080/health >/dev/null 2>&1 " +
            "&& printf healthy || printf waiting"
        )
        $runtimeStatus = Invoke-WslCommand -Capture -Command "bash scripts/native-runtime.sh status"
        Write-Host "  native runtime: $apiHealthy; $runtimeStatus"
        if ($apiHealthy -eq "healthy" -and $runtimeStatus -match "api: running" -and $runtimeStatus -match "worker: running") {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Timed out after $TimeoutSeconds seconds waiting for the native API and worker."
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "wsl.exe was not found. Run this script from Windows PowerShell."
}

$projectExists = Invoke-WslCommand -Capture -Command "test -f compose.yaml && printf yes || printf no"
if ($projectExists -ne "yes") {
    throw "compose.yaml was not found under $ProjectPath."
}

$envExists = Invoke-WslCommand -Capture -Command "test -f .env && printf yes || printf no"
if ($envExists -ne "yes") {
    throw (
        "Missing $ProjectPath/.env. Copy .env.example to .env, replace every " +
        "change-me value, then run this script again."
    )
}

Write-Host "Validating Docker and Compose configuration..."
Invoke-WslCommand -Command "docker info >/dev/null"
Invoke-WslCommand -Command "docker compose config --quiet"

Write-Host "Starting PostgreSQL..."
Invoke-WslCommand -Command "docker compose up -d postgres"
Wait-ForHealthyService -Service "postgres"
Start-Sleep -Seconds $DelaySeconds

Write-Host "Starting Qdrant..."
Invoke-WslCommand -Command "docker compose up -d qdrant"
Wait-ForHealthyService -Service "qdrant"
Start-Sleep -Seconds $DelaySeconds

Write-Host "Starting Neo4j..."
Invoke-WslCommand -Command "docker compose up -d neo4j"
Wait-ForHealthyService -Service "neo4j"
Start-Sleep -Seconds $DelaySeconds

$buildOption = if ($SkipBuild) { "" } else { " --build" }

Write-Host "Running database migrations..."
Invoke-WslCommand -Command "docker compose up -d$buildOption --force-recreate migrate"
Wait-ForCompletedService -Service "migrate"
Start-Sleep -Seconds $DelaySeconds

Write-Host "Starting native WSL API and worker..."
# Earlier releases ran these two processes in Docker. Remove only stale
# GraphRAG containers, then use the BoberDetective-compatible native WSL path
# so Windows loopback LM Studio remains private and reachable.
Invoke-WslCommand -Command "docker compose rm -sf api worker"
Invoke-WslCommand -Command "bash scripts/native-runtime.sh stop"
Invoke-WslCommand -Command "bash scripts/native-runtime.sh start"
Wait-ForNativeRuntime
Start-Sleep -Seconds $DelaySeconds

Write-Host ""
Write-Host "GraphRAG Knowledge Service is running."
Invoke-WslCommand -Command "docker compose ps"
Invoke-WslCommand -Command "bash scripts/native-runtime.sh status"
Write-Host ""
Write-Host "Health: http://127.0.0.1:8080/health"
Write-Host "Ready:  http://127.0.0.1:8080/ready"
Write-Host (
    "PostgreSQL, Qdrant, Neo4j and migrations run in Docker. API and worker run " +
    "natively in WSL, so enabled LM Studio providers use Windows loopback only."
)
