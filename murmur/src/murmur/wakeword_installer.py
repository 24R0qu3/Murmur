"""
In-app installer for the optional openwakeword dependency.

The package is installed into a user-writable side directory so the
main binary stays slim and no system-wide pip access is required.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from platformdirs import user_data_dir

_PACKAGE = "openwakeword"


def get_wakeword_dir() -> Path:
    """Platform-appropriate directory for the wakeword side-install.

    Windows : %LOCALAPPDATA%\\murmur\\wakeword
    macOS   : ~/Library/Application Support/murmur/wakeword
    Linux   : ~/.local/share/murmur/wakeword
    """
    return Path(user_data_dir("murmur", appauthor=False)) / "wakeword"


def inject_wakeword_path() -> bool:
    """Prepend the wakeword side-install dir to sys.path if it exists.

    Call this early in main() so any subsequent ``import openwakeword``
    finds the side-installed package.  Returns True when the dir exists.
    """
    d = get_wakeword_dir()
    if d.exists() and str(d) not in sys.path:
        sys.path.insert(0, str(d))
        return True
    return False


def install_wakeword() -> int:
    """Install openwakeword into the side directory.  Returns the exit code."""
    target = get_wakeword_dir()
    target.mkdir(parents=True, exist_ok=True)

    cmd = _find_install_command(target)
    if cmd is None:
        print(
            "  ERROR: could not find pip, uv, or Python on PATH.\n"
            "  Install one of them and retry, or run:\n"
            f"    pip install {_PACKAGE} --target {target}"
        )
        return 1

    print(f"  Installing {_PACKAGE} to {target} …")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        return result.returncode

    # Verify the install actually worked by checking the package is importable
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
            f"  Install directory: {target}\n"
            f"  Try manually: pip install {_PACKAGE} --target {target}"
        )
        return 1


def _find_install_command(target: Path) -> list[str] | None:
    t = str(target)

    # Prefer pip/pip3/python -m pip over uv for --target installs:
    # uv pip install --target may skip transitive dependencies in some versions.
    for pip in ["pip", "pip3"]:
        if shutil.which(pip):
            return [pip, "install", _PACKAGE, "--target", t, "--upgrade"]

    # python -m pip  (covers py launcher on Windows too)
    candidates = ["python", "python3"]
    if sys.platform == "win32":
        candidates = ["py"] + candidates

    for python in candidates:
        if shutil.which(python):
            return [python, "-m", "pip", "install", _PACKAGE, "--target", t, "--upgrade"]

    # uv as last resort (may have --target dependency issues)
    if shutil.which("uv"):
        return ["uv", "pip", "install", _PACKAGE, "--target", t, "--upgrade"]

    return None
