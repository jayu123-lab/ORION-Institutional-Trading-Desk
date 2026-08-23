$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Repo "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Test-OrionHealth {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
  } catch { return $false }
}

if (-not (Test-OrionHealth)) {
  $apiLog = Join-Path $LogDir "launcher-api.log"
  Start-Process -FilePath (Join-Path $Repo ".venv\Scripts\python.exe") `
    -ArgumentList "-m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000" `
    -WorkingDirectory $Repo -RedirectStandardOutput $apiLog -RedirectStandardError (Join-Path $LogDir "launcher-api.err.log") -WindowStyle Hidden
}

$webDir = Join-Path $Repo "apps\web"
$webLog = Join-Path $LogDir "launcher-web.log"
if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port 3000 -InformationLevel Quiet)) {
  Start-Process -FilePath "npm.cmd" -ArgumentList "run dev" -WorkingDirectory $webDir `
    -RedirectStandardOutput $webLog -RedirectStandardError (Join-Path $LogDir "launcher-web.err.log") -WindowStyle Hidden
}

for ($i = 0; $i -lt 30; $i++) {
  if (Test-OrionHealth) { break }
  Start-Sleep -Seconds 1
}

$browser = Get-Command msedge.exe, chrome.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($browser) {
  Start-Process -FilePath $browser.Source -ArgumentList "--app=http://127.0.0.1:3000/command", "--new-window"
} else {
  Start-Process "http://127.0.0.1:3000/command"
}
