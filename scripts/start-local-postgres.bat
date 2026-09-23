@echo off
setlocal
set "PG=%LOCALAPPDATA%\shenzhi-postgresql"
set "BIN=%PG%\pgsql\bin"
if not exist "%BIN%\pg_ctl.exe" if exist "D:\postgresql\bin\pg_ctl.exe" set "BIN=D:\postgresql\bin"
set "DATA=%PG%\data"
set "LOG=%PG%\postgresql-5432.log"
set "PORT=5432"

if not exist "%BIN%\pg_ctl.exe" (
  echo PostgreSQL binaries not found at %BIN%
  exit /b 1
)

if not exist "%DATA%\PG_VERSION" (
  echo ShenZhi PostgreSQL data directory not found at %DATA%
  echo Initialize the local project database before starting it.
  exit /b 1
)

"%BIN%\pg_isready.exe" -h 127.0.0.1 -p %PORT% >nul 2>&1
if %ERRORLEVEL%==0 (
  echo PostgreSQL already running on 127.0.0.1:%PORT%
  exit /b 0
)

"%BIN%\pg_ctl.exe" -D "%DATA%" -l "%LOG%" -o "-p %PORT% -h 127.0.0.1" start
if errorlevel 1 exit /b 1
"%BIN%\pg_isready.exe" -h 127.0.0.1 -p %PORT%
if errorlevel 1 exit /b 1
endlocal
