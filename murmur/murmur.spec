# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Murmur — builds a single-file executable.

Usage:
    cd murmur
    uv run pyinstaller murmur.spec --noconfirm
"""
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
    "wx",
]

datas:         list = []
binaries:      list = []
hiddenimports: list = [
    "tomllib", "wave",
    # Full stdlib packages needed by openwakeword's dependency chain (requests,
    # tqdm, …) that PyInstaller does not detect automatically from the main app:
    "http", "http.client", "http.cookies", "http.cookiejar",
    "http.server", "http.cookiejar",
    "urllib", "urllib.request", "urllib.parse", "urllib.error", "urllib.response",
    "email", "email.mime", "email.mime.text", "email.mime.multipart",
    "xml.etree.ElementTree",
    "multiprocessing",
]

for _pkg in _COLLECT_PKGS:
    try:
        _d, _b, _h = collect_all(_pkg)
        datas         += _d
        binaries      += _b
        hiddenimports += _h
    except Exception:
        pass

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
    runtime_hooks=[],
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
