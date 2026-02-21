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


class Transcriber:
    def __init__(self, config: Config):
        self._model_name = config.model
        self._language   = config.language
        self._device     = config.device
        self._model      = WhisperModel(config.model, device=config.device)

    def switch_to_cpu(self):
        """Reload the model on CPU (called after a CUDA failure)."""
        print(
            "  WARNING: CUDA unavailable — reloading model on CPU.\n"
            "  Set device = \"cpu\" in config.toml to avoid this at startup."
        )
        self._model  = WhisperModel(self._model_name, device="cpu")
        self._device = "cpu"

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        segments, _ = self._model.transcribe(
            audio, language=self._language, vad_filter=True
        )
        return " ".join(seg.text for seg in segments).strip()
