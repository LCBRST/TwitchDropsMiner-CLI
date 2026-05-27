# PyInstaller spec for the CLI build.
#
# Build with:
#   pyinstaller build_cli.spec
# or use the wrapper script: ./build_cli.sh
#
# This produces a single-file binary in `dist/`. The original tkinter GUI is
# excluded entirely — set EXCLUDE_GUI=0 in the environment if you want to
# include `gui.py`/`cache.py` and the GUI dependencies.

# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

SELF_PATH = str(Path(".").resolve())
if SELF_PATH not in sys.path:
    sys.path.insert(0, SELF_PATH)

# Import after sys.path is set so we can read constants from the project.
from constants import WORKING_DIR, DEFAULT_LANG  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EXCLUDE_GUI = os.environ.get("EXCLUDE_GUI", "1") == "1"
APP_NAME = os.environ.get("APP_NAME", "twitch-drops-miner-cli")
ONE_FILE = os.environ.get("ONE_FILE", "1") == "1"
USE_UPX = os.environ.get("USE_UPX", "0") == "1"
OPTIMIZE_LEVEL = int(os.environ.get("OPTIMIZE", "0") or "0")  # 0/1/2

# ---------------------------------------------------------------------------
# Data files: language packs ship inside the binary so translations work.
# ---------------------------------------------------------------------------

datas: list[tuple[str, str]] = []
for lang_filepath in WORKING_DIR.joinpath("lang").glob("*.json"):
    if lang_filepath.stem != DEFAULT_LANG:
        datas.append((str(lang_filepath), "lang"))

# ---------------------------------------------------------------------------
# Module exclusions: chop out anything the CLI never touches.
# ---------------------------------------------------------------------------

excludes: list[str] = []
if EXCLUDE_GUI:
    excludes += [
        # Tk and family — only the original GUI uses these.
        "tkinter", "_tkinter", "tkinter.ttk", "tkinter.messagebox",
        "tkinter.font", "tkinter.filedialog", "tkinter.colorchooser",
        # Pillow + tray — GUI-only.
        "PIL", "PIL.Image", "PIL.ImageTk", "pystray",
        # GTK on Linux — used by pystray for the system tray.
        "gi", "gi.repository.Gtk", "gi.repository.GObject",
        # Windows GUI integrations.
        "win32api", "win32con", "win32gui", "pythoncom",
        # The project's own GUI modules.
        "gui", "cache",
    ]

# ---------------------------------------------------------------------------
# Hidden imports: things PyInstaller's static analysis can miss.
# ---------------------------------------------------------------------------

hiddenimports: list[str] = []

# ---------------------------------------------------------------------------
# Analysis / build
# ---------------------------------------------------------------------------

a = Analysis(
    ["main.py"],
    pathex=[SELF_PATH],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

if ONE_FILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        strip=False,
        upx=USE_UPX,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        optimize=OPTIMIZE_LEVEL,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        strip=False,
        upx=USE_UPX,
        console=True,
        optimize=OPTIMIZE_LEVEL,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=USE_UPX,
        upx_exclude=[],
        name=APP_NAME,
    )
