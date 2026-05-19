# Start FinAlly Docker container (Windows PowerShell)
$ErrorActionPreference = "Stop"

$ImageName = "finally"
$ContainerName = "finally-app"
$DataVolume = "finally-data"

# Resolve project root (parent of this script's directory) so the script
# can be run from anywhere.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

# Ensure .env exists (required by --env-file)
if (-not (Test-Path ".env")) {
    Write-Host "Error: .env file not found in $ProjectRoot"
    Write-Host "Copy .env.example to .env and fill in your API keys."
    exit 1
}

# Build if requested or if image doesn't exist
$ImageExists = $false
try {
    docker image inspect $ImageName *> $null
    if ($LASTEXITCODE -eq 0) { $ImageExists = $true }
} catch { $ImageExists = $false }

if (($args[0] -eq "--build") -or (-not $ImageExists)) {
    Write-Host "Building FinAlly image..."
    docker build -t $ImageName .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# Stop existing running container if any
$Running = docker ps -q -f "name=^$ContainerName$"
if ($Running) {
    Write-Host "Stopping existing container..."
    docker stop $ContainerName | Out-Null
    docker rm $ContainerName | Out-Null
} else {
    # Container may exist but be stopped — remove it so `docker run` doesn't conflict
    $Existing = docker ps -aq -f "name=^$ContainerName$"
    if ($Existing) {
        docker rm $ContainerName | Out-Null
    }
}

# Start container
docker run -d `
    --name $ContainerName `
    -v "$DataVolume`:/app/db" `
    -p 8000:8000 `
    --env-file .env `
    $ImageName | Out-Null

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "FinAlly is running at: http://localhost:8000"
Write-Host "Stop with: .\scripts\stop_windows.ps1"
