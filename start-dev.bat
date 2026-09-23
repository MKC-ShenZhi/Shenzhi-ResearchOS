@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "WEB=%ROOT%apps\web"
set "BACKEND=%ROOT%apps\backend"
set "PG_SCRIPT=%ROOT%scripts\start-local-postgres.bat"
set "API_URL=http://127.0.0.1:8000"
set "WEB_URL=http://127.0.0.1:3000"

echo.
echo ShenZhi local development
echo =========================

where node >nul 2>&1
if errorlevel 1 (
  echo Node.js is required but was not found on PATH.
  goto :fail
)
where pnpm.cmd >nul 2>&1
if errorlevel 1 (
  echo pnpm is required to run the Web package scripts.
  goto :fail
)
where uv >nul 2>&1
if errorlevel 1 (
  echo uv is required to run the FastAPI backend.
  goto :fail
)

if not exist "%BACKEND%\.env" (
  echo Missing apps\backend\.env. Copy .env.example and configure local values first.
  goto :fail
)
if not exist "%WEB%\.env.local" (
  echo Missing apps\web\.env.local. Copy .env.example and configure the local BFF first.
  goto :fail
)
if not exist "%WEB%\node_modules\.bin\next.cmd" (
  echo Web dependencies are missing. Run: pnpm.cmd --dir apps/web install
  goto :fail
)
if not exist "%BACKEND%\.venv\Scripts\python.exe" (
  echo Backend environment is missing. Run: cd apps\backend ^&^& uv sync
  goto :fail
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$busy = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 3000,8000 }); if ($busy.Count) { $busy | ForEach-Object { Write-Host ('Port ' + $_.LocalPort + ' is already in use by PID ' + $_.OwningProcess) }; exit 1 }"
if errorlevel 1 (
  echo Stop the existing process or configure a different port, then try again.
  goto :fail
)

findstr /C:"127.0.0.1:5432" "%BACKEND%\.env" >nul 2>&1
if not errorlevel 1 goto :start_postgres
findstr /C:"localhost:5432" "%BACKEND%\.env" >nul 2>&1
if not errorlevel 1 goto :start_postgres
goto :start_services

:start_postgres
echo Starting the configured local PostgreSQL instance...
call "%PG_SCRIPT%"
if errorlevel 1 (
  echo PostgreSQL did not start. Backend startup was cancelled.
  goto :fail
)

:start_services
echo Starting FastAPI and Next.js in separate windows...
start "ShenZhi FastAPI :8000" cmd /k "cd /d ""%BACKEND%"" && call uv run uvicorn app.main:app --env-file .env --reload --host 127.0.0.1 --port 8000"
start "ShenZhi Web :3000" cmd /k "cd /d ""%WEB%"" && call pnpm.cmd dev --hostname 127.0.0.1 --port 3000"

echo Waiting for FastAPI...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(60); do { try { $r = Invoke-WebRequest -Uri '%API_URL%/health' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 echo FastAPI did not become healthy within 60 seconds. Check its window.

echo Waiting for Next.js...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(90); do { try { $r = Invoke-WebRequest -Uri '%WEB_URL%/knowledge/scholars' -TimeoutSec 3 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
  echo Next.js did not become ready within 90 seconds. Check its window.
  goto :finish
)

start "" "%WEB_URL%/knowledge/scholars"
echo.
echo Ready: %WEB_URL%/knowledge/scholars
echo Keep the FastAPI and Web windows open while testing. Close each window to stop that service.
goto :finish

:fail
echo.
echo Startup stopped. No existing processes were terminated.

:finish
echo.
pause
endlocal
