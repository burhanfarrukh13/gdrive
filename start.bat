@echo off
setlocal

REM ============================================================
REM Drive Manager - One-click launcher
REM Lives in the same folder as favicon.ico so the .exe build
REM can use it as the icon. Launches the server in
REM .\gdrive-platform\ and opens Chrome to localhost:8000.
REM ============================================================

title Drive Manager
cd /d "%~dp0"

REM --- Locate the platform folder (default: gdrive-platform next to this bat) ---
if "%PLATFORM_DIR%"=="" set "PLATFORM_DIR=%~dp0gdrive-platform"

REM --- Locate Python ---
set "PYTHON_EXE="
where python >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%P in ('where python') do (
        REM Prefer real Python, not the Microsoft Store stub.
        for %%I in ("%%P") do set "PY_DIR=%%~dpI"
        if not exist "!PY_DIR!\python.exe" set "PYTHON_EXE=%%P"
    )
)
if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where py 2^>nul') do (
        set "PYTHON_EXE=%%P"
    )
)

if not defined PYTHON_EXE (
    echo.
    echo  [!] Python was not found on this PC.
    echo      Run install.bat first, or install Python 3.11+ from python.org
    echo      and tick "Add Python to PATH" during the install.
    echo.
    pause
    exit /b 1
)

REM --- Use the project venv if it exists, otherwise fall back to the system Python ---
set "VENV_PY=%PLATFORM_DIR%\venv\Scripts\python.exe"
if exist "%VENV_PY%" set "PYTHON_EXE=%VENV_PY%"

echo.
echo  Drive Manager - starting...
echo    Platform: %PLATFORM_DIR%
echo    Python:   %PYTHON_EXE%
echo.

REM --- Launch the server in a separate window so this launcher can wait + open the browser ---
start "Drive Manager Server" cmd /k "cd /d "%PLATFORM_DIR%" && "%PYTHON_EXE%" run.py"

echo  Waiting for server to come up on http://localhost:8000 ...
:waitloop
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri http://localhost:8000/health -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 goto waitloop

echo  Server is up. Opening browser...

REM --- Prefer Chrome, fall back to the default browser if Chrome isn't installed ---
set "BROWSER="
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "BROWSER=C:\Program Files\Google\Chrome\Application\chrome.exe"
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "BROWSER=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "BROWSER=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if defined BROWSER (
    start "" "%BROWSER%" "http://localhost:8000"
) else (
    start "" "http://localhost:8000"
)

echo.
echo  Drive Manager is running in another window. Close that window to stop the server.
echo  You can close THIS window safely.
echo.
timeout /t 5 /nobreak >nul
exit /b 0
