# Fadeprint – Start unter Windows (Doppelklick auf start.bat ruft dieses Skript auf).
# Nutzt Docker Desktop, falls vorhanden; sonst Python + Node.js (werden bei Bedarf per winget installiert).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Has($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

if ((Has docker) -and ((docker info 2>$null) -ne $null)) {
  Write-Host "Starte mit Docker ..." -ForegroundColor Cyan
  docker compose up --build -d
} else {
  if (-not (Has python)) { Write-Host "Installiere Python ..."; winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements; $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User") }
  if (-not (Has node))   { Write-Host "Installiere Node.js ..."; winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements; $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User") }
  if (-not (Test-Path backend\.venv)) { python -m venv backend\.venv }
  & backend\.venv\Scripts\pip.exe install -q -r backend\requirements.txt
  $env:DEMO_MODE = "true"
  Start-Process -WindowStyle Minimized -WorkingDirectory backend -FilePath ".venv\Scripts\uvicorn.exe" -ArgumentList "app.main:app --port 8000"
  Push-Location frontend
  npm install --no-audit --no-fund
  npm run build
  Start-Process -WindowStyle Minimized -FilePath "npx.cmd" -ArgumentList "next start -p 3000"
  Pop-Location
}
Write-Host "Warte auf Fadeprint ..." -ForegroundColor Cyan
for ($i = 0; $i -lt 120; $i++) { try { Invoke-WebRequest -UseBasicParsing http://localhost:3000/api/health | Out-Null; break } catch { Start-Sleep 2 } }
Start-Process "http://localhost:3000"
Write-Host "Fadeprint laeuft: http://localhost:3000  Demo-Login: demo@demo.example.com / FadeprintDemo1!" -ForegroundColor Green
