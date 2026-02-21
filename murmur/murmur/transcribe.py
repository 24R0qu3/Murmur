import numpy as np
from faster_whisper import WhisperModel

from .config import Config


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
        self.device = _resolve_device(config.device)
        self.compute_type = _resolve_compute_type(config.compute_type, self.device)
        self._auto_detected = config.device == "auto"
        self._model = WhisperModel(
            config.model,
            device=self.device,
            compute_type=self.compute_type,
        )
        self._language = config.language

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        segments, _ = self._model.transcribe(
            audio, language=self._language, vad_filter=True
        )
        return " ".join(seg.text for seg in segments).strip()
