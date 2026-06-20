@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "WORKSPACE=%~dp0"
set "ROOT=%WORKSPACE%opennotebook"
set "FRONTEND=%ROOT%\frontend"
set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
set "ENV_FILE=%ROOT%\.env"
set "DATA_ROOT=%WORKSPACE%open-notebook-data"
set "DB_ROOT=%DATA_ROOT%\surrealdb"
set "DB_PATH=%DB_ROOT:\=/%/database.db"
set "DB_LOG=%DATA_ROOT%\database.log"
set "WORKER_LOG=%DATA_ROOT%\worker.log"
set "FRONTEND_LOG=%DATA_ROOT%\frontend.log"
set "LAUNCH_LOCK=%DATA_ROOT%\launcher.lock"

if /i "%~1"=="backend" goto :backend
if /i "%~1"=="frontend" goto :frontend

title Open Notebook Launcher
echo [Open Notebook] Checking local installation...

if not exist "%ROOT%\run_api.py" (
  echo ERROR: Open Notebook was not found at "%ROOT%".
  goto :failed
)
if not exist "%PYTHON_EXE%" (
  echo ERROR: Python environment is missing. Run "uv sync" in "%ROOT%" first.
  goto :failed
)
if not exist "%FRONTEND%\node_modules" (
  echo ERROR: Frontend dependencies are missing. Run "npm ci" in "%FRONTEND%" first.
  goto :failed
)

call :acquire_launcher_lock
if errorlevel 1 (
  echo [Open Notebook] Another launcher is already starting Open Notebook; waiting for the existing startup.
  call :wait_for_port 5055 120
  if errorlevel 1 (
    echo ERROR: Existing startup did not expose the backend/API on port 5055.
    goto :failed
  )
  call :wait_for_port 3000 120
  if errorlevel 1 (
    echo ERROR: Existing startup did not expose the frontend on port 3000.
    goto :failed
  )
  echo.
  echo Open Notebook is ready: http://localhost:3000
  echo Use the password configured in "opennotebook\.env".
  start "" "http://localhost:3000"
  exit /b 0
)
set "LOCK_ACQUIRED=1"

call :resolve_surreal
if errorlevel 1 goto :failed
call "%PYTHON_EXE%" "%WORKSPACE%scripts\ensure_open_notebook_env.py" "%ENV_FILE%"
if errorlevel 1 goto :failed

if not exist "%DATA_ROOT%" mkdir "%DATA_ROOT%"
if not exist "%DB_ROOT%" mkdir "%DB_ROOT%"

powershell.exe -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $r=$c.BeginConnect('127.0.0.1',5055,$null,$null); if ($r.AsyncWaitHandle.WaitOne(750,$false)) { $c.EndConnect($r); exit 0 }; exit 1 } catch { exit 1 } finally { $c.Close() }" >nul 2>nul
if not errorlevel 1 (
  echo [Open Notebook] Backend/API is already running on port 5055; reusing it.
) else (
  echo [Open Notebook] Starting database, worker and API in one backend window...
  start "Open Notebook - Backend" /min cmd.exe /d /c call "%~f0" backend

  call :wait_for_port 5055 120
  if errorlevel 1 (
    echo ERROR: Backend did not become ready on port 5055.
    echo Check "%DB_LOG%" and "%WORKER_LOG%".
    goto :failed
  )
)

powershell.exe -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $r=$c.BeginConnect('127.0.0.1',3000,$null,$null); if ($r.AsyncWaitHandle.WaitOne(750,$false)) { $c.EndConnect($r); exit 0 }; exit 1 } catch { exit 1 } finally { $c.Close() }" >nul 2>nul
if not errorlevel 1 (
  echo [Open Notebook] Frontend is already running on port 3000; reusing it.
) else (
  echo [Open Notebook] Starting frontend...
  start "Open Notebook - Frontend" /min cmd.exe /d /c call "%~f0" frontend

  call :wait_for_port 3000 120
  if errorlevel 1 (
    echo ERROR: Frontend did not become ready on port 3000.
    echo Check "%FRONTEND_LOG%".
    goto :failed
  )
)

echo.
echo Open Notebook is ready: http://localhost:3000
echo Use the password configured in "opennotebook\.env".
call :release_launcher_lock
start "" "http://localhost:3000"
exit /b 0

:backend
title Open Notebook - Backend
powershell.exe -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $r=$c.BeginConnect('127.0.0.1',5055,$null,$null); if ($r.AsyncWaitHandle.WaitOne(750,$false)) { $c.EndConnect($r); exit 0 }; exit 1 } catch { exit 1 } finally { $c.Close() }" >nul 2>nul
if not errorlevel 1 (
  echo [Open Notebook] Backend/API is already running on port 5055; no new backend started.
  exit /b 0
)

call :resolve_surreal
if errorlevel 1 exit /b 1
call "%PYTHON_EXE%" "%WORKSPACE%scripts\ensure_open_notebook_env.py" "%ENV_FILE%"
if errorlevel 1 exit /b 1
call :load_env
if errorlevel 1 exit /b 1

if not exist "%DATA_ROOT%" mkdir "%DATA_ROOT%"
if not exist "%DB_ROOT%" mkdir "%DB_ROOT%"
set "DATA_FOLDER=%DATA_ROOT%"
set "PYTHONPATH=%ROOT%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not defined OLLAMA_API_BASE set "OLLAMA_API_BASE=http://127.0.0.1:11434"

cd /d "%ROOT%"
powershell.exe -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $r=$c.BeginConnect('127.0.0.1',8000,$null,$null); if ($r.AsyncWaitHandle.WaitOne(750,$false)) { $c.EndConnect($r); exit 0 }; exit 1 } catch { exit 1 } finally { $c.Close() }" >nul 2>nul
if not errorlevel 1 (
  echo [Open Notebook] SurrealDB is already running on port 8000; reusing it.
) else (
  start "" /b "%SURREAL_EXE%" start --user root --pass root --bind 127.0.0.1:8000 --log warn "rocksdb:%DB_PATH%" >"%DB_LOG%" 2>&1
  call :wait_for_port 8000 60
  if errorlevel 1 (
    echo ERROR: SurrealDB did not become ready. Check "%DB_LOG%".
    exit /b 1
  )
)

start "" /b "%PYTHON_EXE%" -m surreal_commands.cli.worker --import-modules commands >"%WORKER_LOG%" 2>&1
"%PYTHON_EXE%" run_api.py
exit /b %errorlevel%

:frontend
title Open Notebook - Frontend
if not exist "%DATA_ROOT%" mkdir "%DATA_ROOT%"
powershell.exe -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $r=$c.BeginConnect('127.0.0.1',3000,$null,$null); if ($r.AsyncWaitHandle.WaitOne(750,$false)) { $c.EndConnect($r); exit 0 }; exit 1 } catch { exit 1 } finally { $c.Close() }" >nul 2>nul
if not errorlevel 1 (
  echo [Open Notebook] Frontend is already running on port 3000; no new frontend started.
  exit /b 0
)
cd /d "%FRONTEND%"
call npm.cmd run dev >"%FRONTEND_LOG%" 2>&1
exit /b %errorlevel%

:resolve_surreal
set "SURREAL_EXE="
for /f "delims=" %%I in ('where surreal.exe 2^>nul') do if not defined SURREAL_EXE set "SURREAL_EXE=%%I"
if not defined SURREAL_EXE set "SURREAL_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Packages\SurrealDB.SurrealDB_Microsoft.Winget.Source_8wekyb3d8bbwe\surreal.exe"
if not exist "%SURREAL_EXE%" (
  echo ERROR: surreal.exe was not found. Install SurrealDB first.
  exit /b 1
)
exit /b 0

:acquire_launcher_lock
if not exist "%DATA_ROOT%" mkdir "%DATA_ROOT%"
mkdir "%LAUNCH_LOCK%" >nul 2>nul
if not errorlevel 1 exit /b 0
powershell.exe -NoProfile -Command "$p=$env:LAUNCH_LOCK; if ((Test-Path -LiteralPath $p) -and ((Get-Date) - (Get-Item -LiteralPath $p).LastWriteTime).TotalMinutes -gt 15) { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue; exit 0 }; exit 1" >nul 2>nul
if not errorlevel 1 (
  mkdir "%LAUNCH_LOCK%" >nul 2>nul
  if not errorlevel 1 exit /b 0
)
exit /b 1

:release_launcher_lock
if defined LOCK_ACQUIRED if exist "%LAUNCH_LOCK%" rmdir "%LAUNCH_LOCK%" >nul 2>nul
set "LOCK_ACQUIRED="
exit /b 0

:generate_key
set "LOCAL_KEY="
for /f "delims=" %%K in ('powershell.exe -NoProfile -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')"') do set "LOCAL_KEY=%%K"
if not defined LOCAL_KEY exit /b 1
exit /b 0

:ensure_env
if not exist "%ENV_FILE%" (
  call :generate_key
  if errorlevel 1 (
    echo ERROR: Failed to generate the local encryption key.
    exit /b 1
  )
  >"%ENV_FILE%" echo OPEN_NOTEBOOK_ENCRYPTION_KEY=!LOCAL_KEY!
  >>"%ENV_FILE%" echo OPEN_NOTEBOOK_PASSWORD=open-notebook-change-me
  >>"%ENV_FILE%" echo SURREAL_URL=ws://127.0.0.1:8000/rpc
  >>"%ENV_FILE%" echo SURREAL_USER=root
  >>"%ENV_FILE%" echo SURREAL_PASSWORD=root
  >>"%ENV_FILE%" echo SURREAL_NAMESPACE=open_notebook
  >>"%ENV_FILE%" echo SURREAL_DATABASE=open_notebook
  exit /b 0
)

set "EXISTING_KEY="
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /c:"OPEN_NOTEBOOK_ENCRYPTION_KEY=" "%ENV_FILE%"`) do set "EXISTING_KEY=%%B"
if defined EXISTING_KEY exit /b 0

call :generate_key
if errorlevel 1 (
  echo ERROR: Failed to repair the local encryption key.
  exit /b 1
)
set "TEMP_ENV=%ENV_FILE%.tmp"
set "KEY_LINE_FOUND="
>"!TEMP_ENV!" (
  for /f "usebackq delims=" %%L in ("%ENV_FILE%") do (
    set "ENV_LINE=%%L"
    if /i "!ENV_LINE:~0,29!"=="OPEN_NOTEBOOK_ENCRYPTION_KEY=" (
      echo OPEN_NOTEBOOK_ENCRYPTION_KEY=!LOCAL_KEY!
      set "KEY_LINE_FOUND=1"
    ) else (
      echo(!ENV_LINE!
    )
  )
)
if not defined KEY_LINE_FOUND >>"!TEMP_ENV!" echo OPEN_NOTEBOOK_ENCRYPTION_KEY=!LOCAL_KEY!
move /y "!TEMP_ENV!" "%ENV_FILE%" >nul
exit /b 0

:load_env
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ENV_FILE%") do if not "%%A"=="" set "%%A=%%B"
if not defined OPEN_NOTEBOOK_ENCRYPTION_KEY (
  echo ERROR: OPEN_NOTEBOOK_ENCRYPTION_KEY is empty in "%ENV_FILE%".
  exit /b 1
)
exit /b 0

:wait_for_port
for /l %%N in (1,1,%~2) do (
  powershell.exe -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $r=$c.BeginConnect('127.0.0.1',%~1,$null,$null); if ($r.AsyncWaitHandle.WaitOne(750,$false)) { $c.EndConnect($r); exit 0 }; exit 1 } catch { exit 1 } finally { $c.Close() }" >nul 2>nul
  if not errorlevel 1 exit /b 0
  powershell.exe -NoProfile -Command "Start-Sleep -Seconds 1" >nul
)
exit /b 1

:failed
call :release_launcher_lock
echo.
echo Startup failed. Review the message above.
pause
exit /b 1
