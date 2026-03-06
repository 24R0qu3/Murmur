"""
In-app installer for the optional openwakeword dependency.

The package is installed into a virtual environment inside a user-writable
side directory so the main binary stays slim and no system-wide pip access
is required.  A venv (rather than pip --target) is used because packages
with native C extensions (numpy, scipy, …) don't work reliably when
installed with --target.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from platformdirs import user_data_dir

_PACKAGE = "openwakeword"


def get_wakeword_dir() -> Path:
    """Platform-appropriate base directory for the wakeword side-install.

    Windows : %LOCALAPPDATA%\\murmur\\wakeword
    macOS   : ~/Library/Application Support/murmur/wakeword
    Linux   : ~/.local/share/murmur/wakeword
    """
    return Path(user_data_dir("murmur", appauthor=False)) / "wakeword"


def get_venv_dir() -> Path:
    """Virtual environment directory inside the wakeword base dir."""
    return get_wakeword_dir() / "venv"


def _find_venv_site_packages(venv_dir: Path) -> Path | None:
    """Return the site-packages directory inside a venv, or None."""
    if sys.platform == "win32":
        sp = venv_dir / "Lib" / "site-packages"
        return sp if sp.exists() else None
    lib = venv_dir / "lib"
    if lib.exists():
        for entry in sorted(lib.iterdir()):
            if entry.is_dir() and entry.name.startswith("python"):
                sp = entry / "site-packages"
                if sp.exists():
                    return sp
    return None


def inject_wakeword_path() -> bool:
    """Prepend the wakeword venv's site-packages to sys.path if it exists.

    Call this early in main() so any subsequent ``import openwakeword``
    finds the side-installed package.  Returns True when a usable directory
    was found and added.
    """
    venv_dir = get_venv_dir()
    if venv_dir.exists():
        sp = _find_venv_site_packages(venv_dir)
        if sp is not None and str(sp) not in sys.path:
            sys.path.insert(0, str(sp))
            return True

    # Legacy fallback: old --target installs (before venv approach)
    legacy = get_wakeword_dir()
    if legacy.exists() and not venv_dir.exists() and str(legacy) not in sys.path:
        sys.path.insert(0, str(legacy))
        return True

    return False


def install_wakeword() -> int:
    """Install openwakeword into a virtual environment.  Returns the exit code."""
    venv_dir = get_venv_dir()
    venv_dir.parent.mkdir(parents=True, exist_ok=True)

    # Remove a broken/incomplete venv from a previous failed install attempt.
    if venv_dir.exists() and _find_venv_site_packages(venv_dir) is None:
        shutil.rmtree(venv_dir)

    print(f"  Creating virtual environment at {venv_dir} …")

    if shutil.which("uv"):
        # uv manages packages itself — no pip needed inside the venv.
        result = subprocess.run(["uv", "venv", str(venv_dir)])
        if result.returncode != 0:
            print("  ERROR: failed to create virtual environment.")
            return result.returncode

        print(f"  Installing {_PACKAGE} …")
        result = subprocess.run(
            ["uv", "pip", "install", "--python", str(venv_dir), _PACKAGE, "--upgrade"]
        )
        if result.returncode != 0:
            return result.returncode

    else:
        # Fall back to a system Python + the venv's own pip.
        python = _find_system_python()
        if python is None:
            print(
                "  ERROR: could not find uv or Python 3 to create a virtual environment.\n"
                "  Install uv (https://docs.astral.sh/uv/) or Python 3, then retry."
            )
            return 1

        result = subprocess.run([python, "-m", "venv", str(venv_dir)])
        if result.returncode != 0:
            print("  ERROR: failed to create virtual environment.")
            return result.returncode

        pip = _find_pip_in_venv(venv_dir)
        if pip is None:
            print("  ERROR: virtual environment created but pip not found inside it.")
            return 1

        print(f"  Installing {_PACKAGE} …")
        result = subprocess.run([str(pip), "install", _PACKAGE, "--upgrade"])
        if result.returncode != 0:
            return result.returncode

    # ── Verify ────────────────────────────────────────────────────────────────
    inject_wakeword_path()
    try:
        import importlib.util

        if importlib.util.find_spec("openwakeword") is None:
            raise ImportError("openwakeword not found after install")
        print("  Done. Restart murmur to enable wake word detection.")
        return 0
    except Exception as e:
        print(
            f"  WARNING: install reported success but openwakeword is not importable: {e}\n"
            f"  Venv directory: {venv_dir}"
        )
        return 1


def _find_system_python() -> str | None:
    """Return a system Python executable suitable for creating a venv."""
    candidates = ["python3", "python"]
    if sys.platform == "win32":
        candidates = ["py"] + candidates
    for python in candidates:
        if shutil.which(python):
            return python
    return None


def _find_pip_in_venv(venv_dir: Path) -> Path | None:
    """Return the pip executable inside a venv created by system Python."""
    if sys.platform == "win32":
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        pip = venv_dir / "bin" / "pip"
    return pip if pip.exists() else None
