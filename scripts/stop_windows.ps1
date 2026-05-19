# Stop FinAlly Docker container (Windows PowerShell)
$ErrorActionPreference = "Stop"

$ContainerName = "finally-app"

$Running = docker ps -q -f "name=^$ContainerName$"
if ($Running) {
    Write-Host "Stopping FinAlly..."
    docker stop $ContainerName | Out-Null
    docker rm $ContainerName | Out-Null
    Write-Host "Stopped. Data volume preserved."
} else {
    $Existing = docker ps -aq -f "name=^$ContainerName$"
    if ($Existing) {
        docker rm $ContainerName | Out-Null
        Write-Host "Removed stopped container. Data volume preserved."
    } else {
        Write-Host "FinAlly is not running."
    }
}
