# PyInstaller spec for DriveManager.exe
# Build with:  pyinstaller --noconfirm DriveManager.spec
# Output:      D:\claude\gdrive\dist\DriveManager.exe

# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

HERE = os.path.abspath(os.getcwd())
ICON_PATH = os.path.join(HERE, "favicon.ico")

a = Analysis(
    [os.path.join(HERE, "launcher.py")],
    pathex=[HERE],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # The launcher uses stdlib only — no third-party packages.
        # Keep excludes minimal; removing too many breaks urllib et al.
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DriveManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # don't compress; the user can if they want
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,        # keep the console so the user sees status
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH if os.path.exists(ICON_PATH) else None,
)
