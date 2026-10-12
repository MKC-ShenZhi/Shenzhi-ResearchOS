@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ShenZhi local development launcher.
rem Run from an elevated terminal with: OPEN

set "ROOT=%~dp0"
set "BACKEND=%ROOT%apps\backend"
set "WEB=%ROOT%apps\web"
set "PG=%LOCALAPPDATA%\shenzhi-postgresql"
set "PGDATA=%PG%\data16"
set "PGBIN=%PG%\pgsql\bin"
if not exist "%PGBIN%\pg_ctl.exe" if exist "D:\postgresql\bin\pg_ctl.exe" set "PGBIN=D:\postgresql\bin"

echo.
echo [ShenZhi] Checking PostgreSQL...
if not exist "%PGBIN%\pg_ctl.exe" (
  echo [ERROR] PostgreSQL binaries were not found.
  echo         Expected: %PGBIN%\pg_ctl.exe
  goto :fail
)
if not exist "%PGDATA%\PG_VERSION" (
  echo [ERROR] PostgreSQL data directory is not initialized:
  echo         %PGDATA%
  echo         PG_VERSION is missing. No data was changed.
  goto :fail
)

"%PGBIN%\pg_isready.exe" -h 127.0.0.1 -p 5433 >nul 2>&1
if errorlevel 1 (
  echo [ShenZhi] Starting PostgreSQL on 127.0.0.1:5433...
  "%PGBIN%\pg_ctl.exe" -D "%PGDATA%" -l "%PG%\postgresql-5433.log" -o "-p 5433 -h 127.0.0.1" -w -t 30 start
  if errorlevel 1 (
    echo [ERROR] PostgreSQL failed to start. See:
    echo         %PG%\postgresql-5433.log
    goto :fail
  )
) else (
  echo [OK] PostgreSQL is already running on 127.0.0.1:5433
)

echo [ShenZhi] Starting FastAPI on 127.0.0.1:8000...
start "ShenZhi FastAPI" /D "%BACKEND%" cmd /k "set PYTHONPATH=%BACKEND%&& uv run --locked uvicorn app.main:app --env-file .env --reload --host 127.0.0.1 --port 8000"

echo [ShenZhi] Starting Next.js on localhost:3000...
start "ShenZhi Next.js" /D "%WEB%" cmd /k "pnpm.cmd dev"

echo [ShenZhi] Waiting for services...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$deadline=(Get-Date).AddSeconds(60); do { $api=$false; $web=$false; try { $api=(Test-NetConnection 127.0.0.1 -Port 8000 -InformationLevel Quiet) } catch {}; try { $web=(Test-NetConnection 127.0.0.1 -Port 3000 -InformationLevel Quiet) } catch {}; if($api -and $web){ exit 0 }; Start-Sleep -Milliseconds 500 } while((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
  echo [WARN] Services did not both become ready within 60 seconds.
  echo        Check the FastAPI and Next.js windows for details.
  goto :done
)

echo.
echo ============================================================
echo ShenZhi services are ready.
echo Frontend: http://localhost:3000
echo Backend:  http://127.0.0.1:8000
echo Health:   http://127.0.0.1:8000/health
echo ============================================================
echo Keep the two service windows open while testing.
goto :done

:fail
echo.
echo Startup stopped. Fix the error above and run OPEN again.
exit /b 1

:done
endlocal
