# -*- mode: python ; coding: utf-8 -*-
# Windows one-file build for the Remastered edition.
#
# Built by .github/workflows/build-windows-remastered.yml, which runs from the
# repo root. PyInstaller resolves Analysis() script paths and EXE(icon=) against
# the *current working directory*, not the spec file, so every path here is
# anchored to the spec file's own directory via SPECPATH.
import os

from PyInstaller.utils.hooks import collect_submodules

HERE = os.path.dirname(os.path.abspath(SPEC))
SRC = os.path.join(HERE, "run_remastered.py")
ASSETS = os.path.join(HERE, "TheQuestionGameRemastered", "assets")
ICON = os.path.join(ASSETS, "windowq.ico")

hiddenimports = ['cv2', 'numpy', 'requests', 'pygame']
hiddenimports += collect_submodules('pyttsx3')
# The desktop eye overlay. Imported lazily by run_remastered.py, so name it
# explicitly or PyInstaller may leave it out.
hiddenimports += ['TheQuestionGameRemastered.eye_overlay']


a = Analysis(
    [SRC],
    pathex=[HERE],
    binaries=[],
    datas=[(ASSETS, 'assets')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # tkinter is only used by the macOS overlay; the Windows overlay is Win32.
    excludes=['tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TheQuestionGameRemastered',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON],
)
