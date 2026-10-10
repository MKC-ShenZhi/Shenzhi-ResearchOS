<##
.SYNOPSIS
  Start the ShenZhi local PostgreSQL, FastAPI, and Next.js services in order.

.DESCRIPTION
  This is a development launcher only. It does not run migrations automatically.
  Run Alembic explicitly after reviewing the migration plan:
    cd apps/backend
    uv run --locked --env-file .env alembic upgrade head
##>
[CmdletBinding()]
param(
  [switch]$SkipWeb,
  [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'apps\backend'
$Web = Join-Path $Root 'apps\web'
$Logs = Join-Path $Root '.local-logs'
New-Item -ItemType Directory -Force $Logs | Out-Null

function Wait-HttpOk([string]$Url, [string]$Name) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
      if ($response.StatusCode -eq 200) {
        Write-Host "$Name ready: $Url" -ForegroundColor Green
        return
      }
    } catch { }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  throw "$Name did not become ready within $TimeoutSeconds seconds: $Url"
}

Write-Host 'Starting PostgreSQL...' -ForegroundColor Cyan
$pgResult = & cmd /c (Join-Path $Root 'scripts\start-local-postgres.bat') 2>&1
if ($LASTEXITCODE -ne 0) {
  $pgResult | Write-Host
  throw 'PostgreSQL startup failed.'
}
$pgResult | Write-Host

function Start-DevProcess([string]$Name, [string]$FilePath, [string[]]$ArgumentList, [string]$WorkingDirectory) {
  $out = Join-Path $Logs "$Name.out.log"
  $err = Join-Path $Logs "$Name.err.log"
  Remove-Item $out, $err -Force -ErrorAction SilentlyContinue
  $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory `
    -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
  Write-Host "$Name launcher started (pid $($process.Id)); logs: $out / $err" -ForegroundColor DarkGray
  return $process
}

Write-Host 'Starting FastAPI...' -ForegroundColor Cyan
$backendProcess = Start-DevProcess 'backend' 'uv.exe' @('run', 'uvicorn', 'app.main:app', '--env-file', '.env', '--reload', '--host', '127.0.0.1', '--port', '8000') $Backend
Wait-HttpOk 'http://127.0.0.1:8000/health' 'FastAPI'

if (-not $SkipWeb) {
  Write-Host 'Starting Next.js...' -ForegroundColor Cyan
  $webProcess = Start-DevProcess 'web' 'cmd.exe' @('/d', '/c', 'pnpm.cmd', 'dev') $Web
  Wait-HttpOk 'http://127.0.0.1:3000/' 'Next.js'
  Wait-HttpOk 'http://127.0.0.1:3000/api/v1/chat/config' 'BFF'
}

Write-Host 'Local services are ready.' -ForegroundColor Green
