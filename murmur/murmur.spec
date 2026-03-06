# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Murmur — builds a single-file executable.

Usage:
    cd murmur
    uv run pyinstaller murmur.spec --noconfirm
"""
import glob as _glob
import os as _os
import sys
from PyInstaller.utils.hooks import collect_all

# ── Collect packages that use dynamic imports / native extensions ─────────────

_COLLECT_PKGS = [
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    "huggingface_hub",
    "sounddevice",
    "av",
    "numpy",
]

datas:         list = []
binaries:      list = []
hiddenimports: list = ["tomllib", "wave", "tkinter", "tkinter.ttk", "_tkinter"]

for _pkg in _COLLECT_PKGS:
    try:
        _d, _b, _h = collect_all(_pkg)
        datas         += _d
        binaries      += _b
        hiddenimports += _h
    except Exception:
        pass

# ── Bundle Tcl/Tk for the tkinter GUI overlay ─────────────────────────────────
# python-build-standalone (used by uv) ships its own Tcl/Tk 9.x alongside the
# Python interpreter.  PyInstaller's hook-_tkinter.py often misses these libs
# on Linux because it cannot follow the $ORIGIN-relative RPATH in _tkinter.so.
# We explicitly walk the Python home's lib/ directory and collect everything.

if sys.platform != "win32":
    def _collect_tcl_tk():
        _bins, _tk_datas = [], []
        _seen = set()

        def _add_lib(path):
            real = _os.path.realpath(path)
            if real not in _seen and _os.path.exists(real):
                _seen.add(real)
                _bins.append((real, "."))

        # Method 1: python-build-standalone layout — <home>/lib/libtcl*.so
        # Use realpath to resolve the venv symlink (sys.executable in a uv venv
        # points to .venv/bin/python3.11, not the actual python-build-standalone
        # binary, so dirname/dirname lands in the venv dir instead of the real
        # Python home where libtcl9.0.so lives).
        _home = _os.path.dirname(_os.path.dirname(_os.path.realpath(sys.executable)))
        _lib  = _os.path.join(_home, "lib")
        if _os.path.isdir(_lib):
            for _pat in ("libtcl*.so*", "libtk*.so*"):
                for _p in _glob.glob(_os.path.join(_lib, _pat)):
                    _add_lib(_p)
            # Tcl/Tk library directories (contain init.tcl, tk.tcl, …)
            for _pat in ("tcl[0-9]*", "tk[0-9]*"):
                for _p in _glob.glob(_os.path.join(_lib, _pat)):
                    if _os.path.isdir(_p):
                        _tk_datas.append((_p, _os.path.basename(_p)))

        # Method 2: ldd fallback — ask the linker what _tkinter.so actually needs.
        # This catches cases where python-build-standalone stores the libs elsewhere.
        if not _bins:
            import importlib.util as _ilu
            import subprocess as _sp
            _tkspec = _ilu.find_spec("_tkinter")
            if _tkspec and _tkspec.origin:
                try:
                    _out = _sp.check_output(
                        ["ldd", _tkspec.origin], text=True, stderr=_sp.DEVNULL
                    )
                    for _line in _out.splitlines():
                        if "libtcl" not in _line and "libtk" not in _line:
                            continue
                        _parts = _line.strip().split()
                        if "=>" in _parts:
                            _idx = _parts.index("=>")
                            if _idx + 1 < len(_parts) and _parts[_idx + 1] not in ("", "not"):
                                _add_lib(_parts[_idx + 1])
                except Exception:
                    pass

        return _bins, _tk_datas

    try:
        _tcl_bins, _tcl_datas = _collect_tcl_tk()
        binaries += _tcl_bins
        datas    += _tcl_datas
        if _tcl_bins or _tcl_datas:
            print(f"  Tcl/Tk: bundling {len(_tcl_bins)} libs, {len(_tcl_datas)} data dirs")
        else:
            print("  WARNING: Tcl/Tk libs not found — GUI overlay may be unavailable")
    except Exception as _e:
        print(f"  WARNING: Tcl/Tk collection error: {_e}")

# ── Platform-specific backends ────────────────────────────────────────────────

if sys.platform == "win32":
    hiddenimports += [
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "pystray._win32",
        "pyautogui",
        "pyperclip",
        "win32api", "win32con", "win32gui",
    ]
else:
    hiddenimports += [
        "pynput.keyboard._xorg",
        "pynput.keyboard._uinput",
        "pynput.mouse._xorg",
        "pynput.mouse._dummy",
        "pystray._appindicator",
        "pystray._gtk",
    ]

# ── Build ─────────────────────────────────────────────────────────────────────

a = Analysis(
    ["run.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=["runtime_hook_tkinter.py"],
    # openwakeword is an optional extra — not bundled
    excludes=["openwakeword"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="murmur",
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # keep terminal for status output / headless use
    icon=None,
)
