"""
In-app installer for CUDA runtime libraries.

Installs nvidia-cublas-cu12, nvidia-cudnn-cu12, and nvidia-cuda-runtime-cu12
into a uv-managed side-venv so the murmur binary can find the CUDA DLLs
without requiring the CUDA Toolkit to be installed system-wide.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from platformdirs import user_data_dir

_PACKAGES = [
    "nvidia-cublas-cu12",
    "nvidia-cudnn-cu12",
    "nvidia-cuda-runtime-cu12",
]
_PY_VER = f"{sys.version_info.major}.{sys.version_info.minor}"

_UV_INSTALL_HINT = (
    "  Install uv first:\n"
    + (
        '    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
        if sys.platform == "win32"
        else "    curl -LsSf https://astral.sh/uv/install.sh | sh"
    )
    + "\n  Then open a new terminal and re-run:  murmur --install-cuda"
)

# DLL subdirectory layout inside each nvidia-* package
_WIN_SUBDIRS = ["nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_runtime/bin"]
_LIN_SUBDIRS = ["nvidia/cublas/lib", "nvidia/cudnn/lib", "nvidia/cuda_runtime/lib"]


def get_cuda_dir() -> Path:
    """Platform-appropriate base directory for the CUDA side-install."""
    return Path(user_data_dir("murmur", appauthor=False)) / "cuda"


def get_cuda_venv_dir() -> Path:
    return get_cuda_dir() / "venv"


def _find_site_packages(venv_dir: Path) -> Path | None:
    if sys.platform == "win32":
        sp = venv_dir / "Lib" / "site-packages"
        return sp if sp.exists() else None
    lib = venv_dir / "lib"
    if not lib.exists():
        return None
    for entry in sorted(lib.iterdir()):
        if entry.is_dir() and entry.name == f"python{_PY_VER}":
            sp = entry / "site-packages"
            if sp.exists():
                return sp
    for entry in sorted(lib.iterdir()):
        if entry.is_dir() and entry.name.startswith("python"):
            sp = entry / "site-packages"
            if sp.exists():
                return sp
    return None


def get_cuda_dll_dirs() -> list[str]:
    """Return DLL/SO directories from the murmur CUDA side-install."""
    sp = _find_site_packages(get_cuda_venv_dir())
    if sp is None:
        return []
    subdirs = _WIN_SUBDIRS if sys.platform == "win32" else _LIN_SUBDIRS
    return [str(d) for sub in subdirs if (d := sp / sub.replace("/", os.sep)).is_dir()]


def install_cuda() -> int:
    """Install CUDA runtime libraries into a uv-managed venv. Returns exit code."""
    uv = shutil.which("uv")
    if uv is None:
        print(f"  ERROR: uv is required to install CUDA libraries.\n{_UV_INSTALL_HINT}")
        return 1

    venv_dir = get_cuda_venv_dir()
    venv_dir.parent.mkdir(parents=True, exist_ok=True)

    print(f"  Creating virtual environment (Python {_PY_VER}) at {venv_dir} …")
    result = subprocess.run([uv, "venv", "--python", _PY_VER, str(venv_dir)])
    if result.returncode != 0:
        print("  ERROR: failed to create virtual environment.")
        return result.returncode

    print(f"  Installing {', '.join(_PACKAGES)} …")
    result = subprocess.run(
        [uv, "pip", "install", "--python", str(venv_dir)] + _PACKAGES + ["--upgrade"]
    )
    if result.returncode != 0:
        return result.returncode

    dll_dirs = get_cuda_dll_dirs()
    if not dll_dirs:
        print("  WARNING: CUDA DLLs not found after install — something went wrong.")
        return 1

    print("  Done. Restart murmur to use CUDA acceleration.")
    return 0
