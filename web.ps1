# Cloudra web frontend launcher (Windows PowerShell)
# Usage: .\web.ps1 [-Browser] [-SkipBuild]

param(
    [switch]$Browser,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$Python = if ($env:CLOUDRA_PYTHON) { $env:CLOUDRA_PYTHON } else { "python" }

if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "Node.js and npm are required. Install Node.js >= 18 from https://nodejs.org/"
    exit 1
}
& $Python -c "import cloudra" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python package 'cloudra' is not installed. Run .\install.ps1 first."
    exit 1
}

Set-Location $Frontend
if (-not (Test-Path node_modules)) {
    Write-Host "[web.ps1] installing frontend dependencies..."
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
if (-not $SkipBuild) {
    Write-Host "[web.ps1] building frontend..."
    npm run build
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

if (-not $Browser) {
    Write-Host "[web.ps1] starting Electron..."
    npm run electron
    exit $LASTEXITCODE
}

$Port = if ($env:CLOUDRA_API_PORT) { $env:CLOUDRA_API_PORT } else { "8000" }
$Store = if ($env:CLOUDRA_RUNTIME_STORE) { $env:CLOUDRA_RUNTIME_STORE } else { (Join-Path $Root "runtime-v2.db") }

Write-Host "[web.ps1] starting runtime v2 on http://127.0.0.1:$Port"
$env:CLOUDRA_RUNTIME_STORE = $Store
$Runtime = Start-Process -PassThru -FilePath $Python -ArgumentList @(
    "-m", "uvicorn", "cloudra.services.api_v2:create_default_v2_app",
    "--factory", "--host", "127.0.0.1", "--port", $Port, "--log-level", "warning"
)
Start-Sleep -Seconds 2
Write-Host "[web.ps1] serving frontend at http://127.0.0.1:5173"
$Web = Start-Process -PassThru -FilePath $Python -ArgumentList @(
    "-m", "http.server", "5173", "--bind", "127.0.0.1", "--directory", "$Frontend\dist"
)
Write-Host "[web.ps1] open http://127.0.0.1:5173 (Ctrl+C does not kill child processes; close this window or use Stop-Process)"
Wait-Process -Id $Runtime.Id, $Web.Id
