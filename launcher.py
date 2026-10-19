"""Drive Manager — Windows launcher.

Compiled into DriveManager.exe via PyInstaller and branded with favicon.ico.

What it does, in order:
  1. Finds Python 3.11+ on PATH (skips the Microsoft Store stub).
  2. Activates the project venv if it exists.
  3. Starts `python run.py` in a new console window.
  4. Polls /health on localhost:8000 until the server is up.
  5. Opens Chrome (or default browser) to http://localhost:8000.

This file is intentionally tiny and uses only the stdlib so the
compiled .exe stays small (~6 MB). All the actual app code lives
in gdrive-platform/ and runs in the spawned Python process.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


HERE = Path(__file__).resolve().parent

# When bundled as a onefile PyInstaller exe, __file__ points inside the
# extracted _MEIxxxxxx temp dir, which doesn't contain gdrive-platform.
# In that case, the real source location is the directory of sys.executable.
def _resolve_here() -> Path:
    here = Path(__file__).resolve().parent
    # PyInstaller onefile sets sys._MEIPASS to the temp dir; the user's
    # actual installation lives next to the .exe (i.e. next to sys.executable).
    if getattr(sys, "frozen", False) or "_MEIPASS" in str(here):
        return Path(sys.executable).resolve().parent
    return here


HERE = _resolve_here()


def _find_platform() -> Path:
    """Locate gdrive-platform/.

    Order:
      1. $PLATFORM_DIR env var (explicit override).
      2. <HERE>/gdrive-platform  (EXE lives next to the platform folder)
      3. <HERE>/../gdrive-platform (EXE lives in a subfolder like dist/)
      4. CWD/gdrive-platform  (last-resort fallback)
    """
    env = os.environ.get("PLATFORM_DIR")
    if env:
        p = Path(env)
        if p.exists():
            return p
    candidates = [
        HERE / "gdrive-platform",
        HERE.parent / "gdrive-platform",
        Path.cwd() / "gdrive-platform",
    ]
    for c in candidates:
        if c.exists():
            return c
    return HERE / "gdrive-platform"  # default; will fail loudly below


PLATFORM_DIR = _find_platform()
HEALTH_URL = "http://localhost:8000/health"
APP_URL = "http://localhost:8000"


# ----- Python discovery -----------------------------------------------------

def find_python() -> str | None:
    """Return the path to a real Python 3.11+ executable, or None.

    Skips the Microsoft Store stub at %LOCALAPPDATA%\\Microsoft\\WindowsApps\\
    because it doesn't actually ship an interpreter — it just opens the Store.
    """
    candidates: list[str] = []

    # 1) Venv, if one was created by the installer.
    venv_py = PLATFORM_DIR / "venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        candidates.append(str(venv_py))

    # 2) System Python on PATH.
    for name in ("python", "python3", "py"):
        path = shutil.which(name)
        if path:
            candidates.append(path)

    for path in candidates:
        # Reject the Microsoft Store stub.
        if "WindowsApps" in path:
            continue
        try:
            out = subprocess.check_output(
                [path, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                stderr=subprocess.DEVNULL, text=True,
            ).strip()
        except (subprocess.CalledProcessError, OSError):
            continue
        try:
            major, minor = (int(x) for x in out.split("."))
        except ValueError:
            continue
        if (major, minor) >= (3, 11):
            return path

    return None


def missing_python_dialog() -> None:
    """Show a friendly error when Python isn't available."""
    msg = (
        "Drive Manager could not find Python 3.11 or newer on this PC.\n\n"
        "Run install.bat (in the same folder as this exe) to install it\n"
        "automatically, or install Python manually from python.org and make\n"
        'sure to tick "Add Python to PATH" during the install.'
    )
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "Drive Manager", 0x10)
        except Exception:
            print(msg)
    else:
        print(msg)


# ----- Server lifecycle -----------------------------------------------------

def start_server(python_exe: str) -> subprocess.Popen:
    """Launch the uvicorn server in a new console window."""
    CREATE_NEW_CONSOLE = 0x00000010  # only honored on Windows
    return subprocess.Popen(
        [python_exe, "run.py"],
        cwd=str(PLATFORM_DIR),
        creationflags=CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )


def wait_for_server(timeout_sec: int = 30) -> bool:
    """Poll /health until the server responds or we time out."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    return False


# ----- Browser --------------------------------------------------------------

def find_chrome() -> str | None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def open_browser() -> None:
    chrome = find_chrome()
    if chrome:
        subprocess.Popen([chrome, APP_URL], close_fds=True)
    else:
        # Fall back to the OS default browser.
        if sys.platform == "win32":
            os.startfile(APP_URL)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", APP_URL])


# ----- Main -----------------------------------------------------------------

def main() -> int:
    print("Drive Manager - starting...")
    print(f"  Platform: {PLATFORM_DIR}")

    python_exe = find_python()
    if not python_exe:
        print("  Python:   NOT FOUND")
        missing_python_dialog()
        return 1
    print(f"  Python:   {python_exe}")

    if not PLATFORM_DIR.exists():
        print(f"\n  ERROR: Platform folder not found: {PLATFORM_DIR}")
        print("  Re-run install.bat to repair the installation.")
        return 1

    print("\n  Starting server...")
    server = start_server(python_exe)
    try:
        print("  Waiting for http://localhost:8000 ...")
        if not wait_for_server(timeout_sec=45):
            print("  ERROR: Server did not start within 45 seconds.")
            print("  Check the 'Drive Manager Server' window for the actual error.")
            return 2
        print("  Server is up. Opening browser...")
        open_browser()
        print("\n  Drive Manager is running. Close the 'Drive Manager Server'")
        print("  window to stop the server. You can close this window too.")
        return 0
    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
        return 130
    finally:
        # Don't kill the server process on exit — the user closes the
        # server window to stop it. Detach so the child survives.
        try:
            if server.poll() is None:
                # On Windows, the child already owns its own console.
                pass
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
