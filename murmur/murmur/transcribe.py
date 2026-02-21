import numpy as np
from faster_whisper import WhisperModel

from .config import Config


class Transcriber:
    def __init__(self, config: Config):
        self._model = WhisperModel(config.model, device=config.device)
        self._language = config.language

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        segments, _ = self._model.transcribe(
            audio, language=self._language, vad_filter=True
        )
        return " ".join(seg.text for seg in segments).strip()
