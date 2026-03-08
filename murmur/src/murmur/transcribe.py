import glob
import os
import site
import sys

import numpy as np

from .config import Config


def _add_cuda_dll_dirs() -> None:
    """
    On Windows, ctranslate2 finds CUDA DLLs via PATH (not AddDllDirectory).
    Prepend pip-installed nvidia-* package bin dirs and CUDA Toolkit bin to PATH.
    Must be called BEFORE importing faster_whisper / ctranslate2.
    """
    if sys.platform != "win32":
        return

    dirs: list[str] = []

    # pip-installed nvidia-cublas-cu12 / nvidia-cudnn-cu12 / nvidia-cuda-runtime-cu12
    for site_dir in site.getsitepackages():
        for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_runtime/bin"):
            dll_dir = os.path.join(site_dir, sub.replace("/", os.sep))
            if os.path.isdir(dll_dir):
                dirs.append(dll_dir)

    # murmur --install-cuda side-install
    try:
        from .cuda_installer import get_cuda_dll_dirs

        dirs.extend(d for d in get_cuda_dll_dirs() if d not in dirs)
    except Exception:
        pass

    # CUDA_PATH env var set by the NVIDIA CUDA Toolkit installer
    cuda_path = os.environ.get("CUDA_PATH") or os.environ.get("CUDA_HOME")
    if cuda_path:
        bin_dir = os.path.join(cuda_path, "bin")
        if os.path.isdir(bin_dir):
            dirs.append(bin_dir)

    # Conda / mamba environments
    conda_prefix = os.environ.get("CONDA_PREFIX") or os.environ.get("CONDA_DEFAULT_ENV")
    if conda_prefix and os.path.isabs(conda_prefix):
        conda_bin = os.path.join(conda_prefix, "Library", "bin")
        if os.path.isdir(conda_bin):
            dirs.append(conda_bin)

    # System CUDA Toolkit install (common default locations)
    for pattern in [
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v*\bin",
        r"C:\CUDA\v*\bin",
    ]:
        for path in sorted(glob.glob(pattern), reverse=True):
            if os.path.isdir(path):
                dirs.append(path)

    if dirs:
        os.environ["PATH"] = (
            os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")
        )


# Must run before faster_whisper / ctranslate2 are imported
_add_cuda_dll_dirs()

try:
    import onnxruntime as _ort

    _ort.set_default_logger_severity(3)  # ERROR only — suppress GPU discovery warnings
except Exception:
    pass

from faster_whisper import WhisperModel  # noqa: E402


def detect_device() -> str:
    """Return 'cuda' if a CUDA-capable CTranslate2 build with visible GPU is found, else 'cpu'.
    Safe to call on any platform — all failure modes are caught."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _resolve_device(requested: str) -> str:
    return detect_device() if requested == "auto" else requested


def _resolve_compute_type(requested: str, device: str) -> str:
    if requested != "auto":
        return requested
    return "float16" if device == "cuda" else "int8_float32"


class Transcriber:
    def __init__(self, config: Config):
        self._model_name = config.model
        self._language = config.language
        self.device = _resolve_device(config.device)
        self.compute_type = _resolve_compute_type(config.compute_type, self.device)
        self._auto_detected = config.device == "auto"
        try:
            self._model = WhisperModel(
                config.model,
                device=self.device,
                compute_type=self.compute_type,
            )
        except ValueError as exc:
            if "compute type" in str(exc).lower() and self.compute_type == "float16":
                print(
                    "  WARNING: float16 not supported on this device — falling back to int8_float32.\n"
                    '  Set compute_type = "int8_float32" in config.toml to silence this.'
                )
                self.compute_type = "int8_float32"
                self._model = WhisperModel(
                    config.model,
                    device=self.device,
                    compute_type=self.compute_type,
                )
            else:
                raise

    def switch_to_cpu(self):
        """Reload the model on CPU (called after a CUDA failure)."""
        print(
            "  WARNING: CUDA unavailable — reloading model on CPU.\n"
            "  Run:  murmur --install-cuda  to install CUDA libraries.\n"
            '  Or set device = "cpu" in config.toml to silence this warning.'
        )
        self._model = WhisperModel(self._model_name, device="cpu")
        self.device = "cpu"

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        segments, _ = self._model.transcribe(
            audio, language=self._language, vad_filter=True
        )
        return " ".join(seg.text for seg in segments).strip()
