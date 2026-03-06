"""
In-app installer for the optional openwakeword dependency.

uv is the only supported installer.  It creates a virtual environment pinned
to the same Python major.minor as the running interpreter (critical for binary
distributions where the embedded Python version is fixed) and installs
openwakeword into it.  No system Python fallback — uv can download the right
Python version automatically if it is not already present on the system.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from platformdirs import user_data_dir

_PACKAGE = "openwakeword"
_PY_VER = f"{sys.version_info.major}.{sys.version_info.minor}"

_UV_INSTALL_HINT = (
    "  Install uv first:\n"
    "    curl -LsSf https://astral.sh/uv/install.sh | sh\n"
    "  Then open a new terminal and re-run:  murmur --install-wakeword"
)


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
    if not lib.exists():
        return None
    # Prefer an exact Python version match so C-extension ABI is guaranteed.
    target = f"python{_PY_VER}"
    for entry in sorted(lib.iterdir()):
        if entry.is_dir() and entry.name == target:
            sp = entry / "site-packages"
            if sp.exists():
                return sp
    # Fallback: any python* directory (covers edge cases).
    for entry in sorted(lib.iterdir()):
        if entry.is_dir() and entry.name.startswith("python"):
            sp = entry / "site-packages"
            if sp.exists():
                return sp
    return None


def inject_wakeword_path() -> bool:
    """Prepend the wakeword venv's site-packages to sys.path if it exists."""
    venv_dir = get_venv_dir()
    if venv_dir.exists():
        sp = _find_venv_site_packages(venv_dir)
        if sp is not None and str(sp) not in sys.path:
            sys.path.insert(0, str(sp))
            return True
    return False


def install_wakeword() -> int:
    """Install openwakeword into a uv-managed venv.  Returns the exit code."""
    uv = shutil.which("uv")
    if uv is None:
        print(
            f"  ERROR: uv is required to install the wake word support.\n{_UV_INSTALL_HINT}"
        )
        return 1

    venv_dir = get_venv_dir()
    venv_dir.parent.mkdir(parents=True, exist_ok=True)

    # Remove a stale venv if it targets the wrong Python version or is broken.
    if venv_dir.exists():
        sp = _find_venv_site_packages(venv_dir)
        wrong_version = sp is not None and f"python{_PY_VER}" not in str(sp)
        if sp is None or wrong_version:
            print("  Removing incompatible venv …")
            import shutil as _sh

            _sh.rmtree(venv_dir)

    print(f"  Creating virtual environment (Python {_PY_VER}) at {venv_dir} …")
    result = subprocess.run([uv, "venv", "--python", _PY_VER, str(venv_dir)])
    if result.returncode != 0:
        print("  ERROR: failed to create virtual environment.")
        return result.returncode

    print(f"  Installing {_PACKAGE} …")
    result = subprocess.run(
        [uv, "pip", "install", "--python", str(venv_dir), _PACKAGE, "--upgrade"]
    )
    if result.returncode != 0:
        return result.returncode

    # Verify
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
