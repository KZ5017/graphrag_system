[CmdletBinding()]
param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$WslUser = "bober",
    [string]$ProjectPath = "/home/bober/projects/graphrag_system",
    [ValidateRange(5, 120)]
    [int]$ShutdownTimeoutSeconds = 30
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

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "wsl.exe was not found. Run this script from Windows PowerShell."
}

$projectExists = Invoke-WslCommand -Capture -Command "test -f compose.yaml && printf yes || printf no"
if ($projectExists -ne "yes") {
    throw "compose.yaml was not found under $ProjectPath."
}

Write-Host "Stopping GraphRAG Knowledge Service..."
Invoke-WslCommand -Command "bash scripts/native-runtime.sh stop"

# Placeholder values only satisfy Compose interpolation when .env does not
# exist. They do not alter persisted credentials or volumes during `down`.
$stopCommand = (
    "env GKS_POSTGRES_PASSWORD=stop-only " +
    "GKS_NEO4J_PASSWORD=stop-only " +
    "GKS_SERVICE_TOKEN=stop-only-service-token " +
    "docker compose down --remove-orphans --timeout $ShutdownTimeoutSeconds"
)
Invoke-WslCommand -Command $stopCommand

$remaining = Invoke-WslCommand -Capture -Command (
    "docker ps -aq --filter " +
    "label=com.docker.compose.project=graphrag-knowledge-service"
)
if ($remaining) {
    throw "One or more GraphRAG Compose containers are still present: $remaining"
}

Write-Host "All GraphRAG components are stopped."
Write-Host "Persistent PostgreSQL, Qdrant, and Neo4j volumes were preserved."
Write-Host "LM Studio and BoberDetective components were not touched."
