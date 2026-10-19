@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM Drive Manager - One-shot installer
REM
REM What this does, in order:
REM   1. Detects Python 3.11+. If missing, downloads the official
REM      Windows installer from python.org and runs it for the user.
REM   2. Creates a project-local virtualenv at
REM      .\gdrive-platform\venv\
REM   3. Installs requirements.txt into that venv.
REM   4. Builds DriveManager.exe via PyInstaller from launcher.py,
REM      using DriveManager.spec (skips if the exe already exists).
REM   5. Creates a Desktop shortcut to DriveManager.exe (with the
REM      favicon, if favicon.ico is in the same folder as this bat) —
REM      falling back to start.bat if the exe build was skipped/failed.
REM
REM Re-running is safe: each step is a no-op if already done.
REM
REM Usage:
REM   - Double-click install.bat, OR
REM   - From a terminal: install.bat
REM
REM Optional env vars:
REM   SKIP_PYTHON=1     skip the Python download/install check
REM   SKIP_DEPS=1       skip requirements install (offline mode)
REM   SKIP_BUILD=1      skip the DriveManager.exe build step
REM   REBUILD_EXE=1     force a rebuild even if the exe already exists
REM   SKIP_SHORTCUT=1   skip the desktop shortcut step
REM ============================================================

title Drive Manager - Installer
cd /d "%~dp0"

set "PLATFORM_DIR=%~dp0gdrive-platform"
set "PY_MIN_MAJOR=3"
set "PY_MIN_MINOR=11"

echo.
echo  ===========================================================
echo    Drive Manager - Installer
echo  ===========================================================
echo.
echo  This will set up the app on this PC. It may take a few
echo  minutes if Python or the dependencies need to be installed.
echo.
echo  Press Ctrl-C to abort, or any other key to continue.
pause >nul

REM ------------------------------------------------------------
REM 1. Make sure Python is installed and on PATH
REM ------------------------------------------------------------
if not "%SKIP_PYTHON%"=="1" goto :check_python
echo  [skip] SKIP_PYTHON=1, assuming Python is already installed.
goto :python_done

:check_python
echo.
echo  [1/5] Checking for Python %PY_MIN_MAJOR%.%PY_MIN_MINOR%+ ...
set "PYTHON_EXE="
where python >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%P in ('where python') do (
        for %%I in ("%%P") do set "PY_DIR=%%~dpI"
        if not "!PY_DIR!"=="%LOCALAPPDATA%\Microsoft\WindowsApps\" set "PYTHON_EXE=%%P"
    )
)
if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where py 2^>nul') do set "PYTHON_EXE=%%P"
)

if defined PYTHON_EXE (
    for /f "tokens=2 delims= " %%V in ('"!PYTHON_EXE!" --version 2^>^&1') do set "PY_VERSION=%%V"
    echo       Found: !PYTHON_EXE!  (version !PY_VERSION!)
    for /f "tokens=1,2 delims=." %%a in ("!PY_VERSION!") do (
        set "PY_MAJOR=%%a"
        set "PY_MINOR=%%b"
    )
    if !PY_MAJOR! GTR %PY_MIN_MAJOR% goto :python_done
    if !PY_MAJOR! EQU %PY_MIN_MAJOR% if !PY_MINOR! GEQ %PY_MIN_MINOR% goto :python_done
    echo       Version is too old (need %PY_MIN_MAJOR%.%PY_MIN_MINOR%+).
    set "PYTHON_EXE="
)

if defined PYTHON_EXE goto :python_done

echo       Python not found or too old. Downloading the official
echo       Windows installer (64-bit) ...
set "PY_INSTALLER=%TEMP%\python-%PY_MIN_MAJOR%.%PY_MIN_MINOR%-amd64.exe"
set "PY_URL=https://www.python.org/ftp/python/%PY_MIN_MAJOR%.%PY_MIN_MINOR%.9/python-%PY_MIN_MAJOR%.%PY_MIN_MINOR%.9-amd64.exe"
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%' -UseBasicParsing"
if not exist "%PY_INSTALLER%" (
    echo  [!] Download failed. Please install Python %PY_MIN_MAJOR%.%PY_MIN_MINOR%+ manually from https://www.python.org/downloads/
    echo      IMPORTANT: tick "Add python.exe to PATH" during the install.
    pause
    exit /b 1
)
echo       Running the installer (this opens a window) ...
echo       When asked, tick "Add Python to PATH" and "Install for all users".
"%PY_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_doc=0 Include_launcher=1
if errorlevel 1 (
    echo  [!] Installer exited with code %errorlevel%. Try installing Python manually.
    pause
    exit /b 1
)
del "%PY_INSTALLER%" >nul 2>nul

REM Refresh PATH for the rest of this session.
for /f "delims=" %%P in ('where python') do set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE set "PYTHON_EXE=py"
echo       Done.

:python_done
REM ------------------------------------------------------------
REM 2. Create venv if missing
REM ------------------------------------------------------------
echo.
echo  [2/5] Setting up project virtualenv ...
if not exist "%PLATFORM_DIR%\venv\Scripts\python.exe" (
    if not exist "%PLATFORM_DIR%" (
        echo  [!] Platform folder not found: %PLATFORM_DIR%
        echo      Make sure gdrive-platform\ sits next to this installer.
        pause
        exit /b 1
    )
    "%PYTHON_EXE%" -m venv "%PLATFORM_DIR%\venv"
    if errorlevel 1 (
        echo  [!] Failed to create venv.
        pause
        exit /b 1
    )
    echo       Created %PLATFORM_DIR%\venv
) else (
    echo       Already exists, skipping.
)

REM ------------------------------------------------------------
REM 3. Install requirements
REM ------------------------------------------------------------
echo.
echo  [3/5] Installing Python packages ...
if "%SKIP_DEPS%"=="1" (
    echo  [skip] SKIP_DEPS=1, skipping pip install.
    goto :deps_done
)
"%PLATFORM_DIR%\venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"%PLATFORM_DIR%\venv\Scripts\python.exe" -m pip install -r "%PLATFORM_DIR%\requirements.txt"
if errorlevel 1 (
    echo  [!] pip install failed. Check your network connection and try again.
    pause
    exit /b 1
)
echo       Done.
:deps_done

REM ------------------------------------------------------------
REM 4. Build DriveManager.exe (PyInstaller), unless it already exists
REM ------------------------------------------------------------
echo.
echo  [4/5] Building DriveManager.exe ...
set "EXE_PATH=%~dp0DriveManager.exe"
set "SPEC_PATH=%~dp0DriveManager.spec"
if "%SKIP_BUILD%"=="1" (
    echo  [skip] SKIP_BUILD=1, skipping exe build.
    goto :build_done
)
if exist "%EXE_PATH%" if not "%REBUILD_EXE%"=="1" (
    echo       %EXE_PATH% already exists, skipping. ^(set REBUILD_EXE=1 to force^)
    goto :build_done
)
if not exist "%SPEC_PATH%" (
    echo  [!] DriveManager.spec not found next to install.bat — skipping exe build.
    echo      You can still run the app via start.bat.
    goto :build_done
)
"%PLATFORM_DIR%\venv\Scripts\python.exe" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo       Installing PyInstaller into the venv ^(build tool, not a runtime dep^) ...
    "%PLATFORM_DIR%\venv\Scripts\python.exe" -m pip install pyinstaller >nul
    if errorlevel 1 (
        echo  [!] Failed to install PyInstaller. Skipping exe build — use start.bat instead.
        goto :build_done
    )
)
pushd "%~dp0"
"%PLATFORM_DIR%\venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean "%SPEC_PATH%"
set "BUILD_ERR=%errorlevel%"
popd
if not "%BUILD_ERR%"=="0" (
    echo  [!] PyInstaller build failed ^(exit %BUILD_ERR%^). Falling back to start.bat.
    goto :build_done
)
if exist "%~dp0dist\DriveManager.exe" copy /y "%~dp0dist\DriveManager.exe" "%EXE_PATH%" >nul
echo       Built %EXE_PATH%
:build_done

REM ------------------------------------------------------------
REM 5. Create Desktop shortcut
REM ------------------------------------------------------------
echo.
echo  [5/5] Creating Desktop shortcut ...
if "%SKIP_SHORTCUT%"=="1" (
    echo  [skip] SKIP_SHORTCUT=1, skipping shortcut.
    goto :shortcut_done
)
set "ICON_PATH=%~dp0favicon.ico"
if not exist "%ICON_PATH%" set "ICON_PATH="

REM Prefer the compiled exe (branded, self-contained Python/venv detection);
REM fall back to start.bat if the build was skipped or failed.
set "SHORTCUT_TARGET=%~dp0start.bat"
if exist "%EXE_PATH%" set "SHORTCUT_TARGET=%EXE_PATH%"
if "%ICON_PATH%"=="" if exist "%EXE_PATH%" set "ICON_PATH=%EXE_PATH%"

powershell -NoProfile -Command ^
 "$s = (New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Drive Manager.lnk');" ^
 "$s.TargetPath = '%SHORTCUT_TARGET%';" ^
 "$s.WorkingDirectory = '%~dp0';" ^
 "$s.IconLocation = '%ICON_PATH%';" ^
 "$s.Description = 'Drive Manager - Access, Revenue, and Team Manager';" ^
 "$s.Save()"
echo       Created "%USERPROFILE%\Desktop\Drive Manager.lnk" -^> %SHORTCUT_TARGET%

:shortcut_done

echo.
echo  ===========================================================
echo    Installation complete!
echo  ===========================================================
echo.
echo  Next steps:
echo    1. Drop your Google service account JSON into:
echo         %PLATFORM_DIR%\secrets\service_account.json
echo       (See GOOGLE_SETUP.md if you don't have one yet.)
echo    2. Double-click "Drive Manager" on your Desktop to launch.
echo.
echo  Default login: admin@local / admin123  --  change it on first login.
echo.
pause
exit /b 0
