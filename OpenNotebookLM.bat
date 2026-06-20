@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "WORKSPACE=%~dp0"

:: Add common Python and Node install directories to PATH.
set "PATH=%APPDATA%\Python\Python313\Scripts;%APPDATA%\Python\Python313;%USERPROFILE%\.local\bin;C:\nvm4w\nodejs;C:\Program Files\nodejs;%PATH%"

:: Find a Python interpreter
set "PYTHON="
set "PYTHON_ARGS="
for %%c in (python python3) do (
    where %%c >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON=%%c"
        goto :found_python
    )
)
:: Try Python launcher
py -3 --version >nul 2>nul
if not errorlevel 1 set "PYTHON=py" & set "PYTHON_ARGS=-3" & goto :found_python
:: Try AppData install
if exist "%APPDATA%\Python\Python313\python.exe" set "PYTHON=%APPDATA%\Python\Python313\python.exe" & goto :found_python

echo ERROR: No Python interpreter found. Install Python 3.8+.
echo Try: winget install Python.Python.3.13
exit /b 1

:found_python
"%PYTHON%" %PYTHON_ARGS% "%WORKSPACE%scripts\open_notebook_lm.py" %*
exit /b %errorlevel%
