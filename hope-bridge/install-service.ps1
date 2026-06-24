# install-service.ps1
# -------------------
# Installs the Hope Bridge as a Windows service using NSSM.
# Run as Administrator on the DRM Hope PC.
#
# Prerequisites:
#   1. Download NSSM from https://nssm.cc/download
#   2. Extract — copy win64\nssm.exe to C:\Tools\nssm\nssm.exe
#   3. Create C:\hope-bridge\ and copy all files from this directory
#   4. Create C:\hope-bridge\.venv: python -m venv C:\hope-bridge\.venv
#   5. Install deps: C:\hope-bridge\.venv\Scripts\pip install -r C:\hope-bridge\requirements.txt
#   6. Copy .env.example to .env and fill in secrets
#   7. Run this script as Administrator

$ErrorActionPreference = "Stop"

$NssmExe   = "C:\Tools\nssm\nssm.exe"
$PythonExe = "C:\hope-bridge\.venv\Scripts\python.exe"
$AppDir    = "C:\hope-bridge"
$LogDir    = "C:\hope-bridge\logs"
$SvcName   = "HopeBridge"

# Validate prerequisites
if (-not (Test-Path $NssmExe))   { throw "NSSM not found at $NssmExe. Download from https://nssm.cc/download" }
if (-not (Test-Path $PythonExe)) { throw "Python venv not found at $PythonExe. Run: python -m venv C:\hope-bridge\.venv" }
if (-not (Test-Path "$AppDir\.env")) { throw ".env file missing. Copy .env.example to .env and fill in secrets." }

# Create log directory
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Remove existing service if present
$existing = Get-Service -Name $SvcName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Stopping and removing existing $SvcName service..."
    & $NssmExe stop $SvcName 2>$null
    & $NssmExe remove $SvcName confirm
}

Write-Host "Installing $SvcName service..."

& $NssmExe install  $SvcName $PythonExe "-m uvicorn main:app --host 0.0.0.0 --port 7070"
& $NssmExe set      $SvcName AppDirectory  $AppDir
& $NssmExe set      $SvcName Start         SERVICE_AUTO_START
& $NssmExe set      $SvcName AppStdout     "$LogDir\bridge.log"
& $NssmExe set      $SvcName AppStderr     "$LogDir\bridge-err.log"
& $NssmExe set      $SvcName AppRotateFiles 1
& $NssmExe set      $SvcName AppRotateBytes 10485760   # 10 MB

Write-Host "Starting $SvcName..."
Start-Service $SvcName

$status = (Get-Service -Name $SvcName).Status
Write-Host ""
Write-Host "Service status: $status"
Write-Host ""
Write-Host "Hope Bridge is running on http://localhost:7070"
Write-Host "Swagger docs: http://localhost:7070/docs"
Write-Host ""
Write-Host "Logs: $LogDir"
Write-Host "To stop:    Stop-Service $SvcName"
Write-Host "To restart: Restart-Service $SvcName"
Write-Host "To remove:  & `"$NssmExe`" remove $SvcName confirm"
