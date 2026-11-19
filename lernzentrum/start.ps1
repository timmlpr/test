# Lernzentrum local start for Windows. Docker Desktop if present, otherwise installs Python/Node via winget
# (if missing) and runs API + web directly with SQLite in demo mode.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Has($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

if ((Has "docker") -and (docker info 2>$null)) {
    Write-Host "Docker gefunden – starte kompletten Stack ..." -ForegroundColor Green
    Start-Process "http://localhost:3000"
    docker compose up --build
    exit
}
if (-not (Has "python")) {
    Write-Host "Installiere Python 3.13 ..."; winget install -e --id Python.Python.3.13 --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
if (-not (Has "npm")) {
    Write-Host "Installiere Node.js LTS ..."; winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
if (-not (Has "ffmpeg")) {
    Write-Host "Installiere ffmpeg (für Sprachmemos) ..."; winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
}

Push-Location backend
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
Pop-Location
Push-Location frontend
if (-not (Test-Path "node_modules")) { npm ci --no-audit --no-fund }
if (-not (Test-Path ".next")) { npm run build }
Pop-Location

$api = Start-Process -PassThru -WindowStyle Minimized -WorkingDirectory "$PSScriptRoot\backend" `
    -FilePath "$PSScriptRoot\backend\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000"
$web = Start-Process -PassThru -WindowStyle Minimized -WorkingDirectory "$PSScriptRoot\frontend" -FilePath "npx.cmd" -ArgumentList "next start -p 3000"
Start-Sleep -Seconds 5
Start-Process "http://localhost:3000"
Write-Host "Lernzentrum läuft auf http://localhost:3000 (Demo: demo@lernzentrum.app / Lernzentrum2026). Enter beendet." -ForegroundColor Green
Read-Host | Out-Null
Stop-Process -Id $api.Id, $web.Id -ErrorAction SilentlyContinue
