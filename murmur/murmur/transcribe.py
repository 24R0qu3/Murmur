import glob
import os
import sys
import site

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

    # System CUDA Toolkit install
    for pattern in [
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v*\bin",
        r"C:\CUDA\v*\bin",
    ]:
        for path in sorted(glob.glob(pattern), reverse=True):
            if os.path.isdir(path):
                dirs.append(path)

    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")


# Must run before faster_whisper / ctranslate2 are imported
_add_cuda_dll_dirs()

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
        self._model = WhisperModel(
            config.model,
            device=self.device,
            compute_type=self.compute_type,
        )

    def switch_to_cpu(self):
        """Reload the model on CPU (called after a CUDA failure)."""
        print(
            "  WARNING: CUDA unavailable — reloading model on CPU.\n"
            "  Set device = \"cpu\" in config.toml to avoid this at startup."
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
