import queue
import sys
import time
import threading

import numpy as np
import sounddevice as sd

WHISPER_RATE = 16000
CHANNELS = 1
DTYPE = "float32"


def _find_working_config() -> tuple[int | None, int]:
    """
    Probe (device, sample_rate) pairs and return the first combination that
    can actually open and start an InputStream. Runs once at import time.
    """
    candidates: list[tuple[int | None, int]] = []

    if sys.platform == "win32":
        try:
            for api in sd.query_hostapis():
                if "WASAPI" in api["name"] and api["default_input_device"] >= 0:
                    dev = api["default_input_device"]
                    try:
                        native = int(sd.query_devices(dev, "input")["default_samplerate"])
                    except Exception:
                        native = 48000
                    candidates.append((dev, native))
        except Exception:
            pass

    for rate in (48000, 44100, 16000):
        candidates.append((None, rate))

    def _noop(indata, frames, time, status):
        pass

    for device, rate in candidates:
        stream = None
        try:
            stream = sd.InputStream(
                samplerate=rate,
                channels=CHANNELS,
                dtype=DTYPE,
                device=device,
                callback=_noop,
            )
            stream.start()
            stream.stop()
            stream.close()
            return device, rate
        except Exception:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

    return None, WHISPER_RATE


def _resample(audio: np.ndarray, orig_rate: int) -> np.ndarray:
    """Linear-interpolation resample to WHISPER_RATE. No-op if rates match."""
    if orig_rate == WHISPER_RATE or audio.size == 0:
        return audio
    target_len = int(len(audio) * WHISPER_RATE / orig_rate)
    return np.interp(
        np.linspace(0, len(audio) - 1, target_len),
        np.arange(len(audio)),
        audio,
    ).astype(np.float32)


_DEVICE, _RATE = _find_working_config()


class AudioRecorder:
    """
    Keeps a single InputStream open for the lifetime of the process.
    Recording is toggled via a flag — no stream open/close per keypress,
    which avoids COM thread-affinity issues on Windows.
    """

    def __init__(self):
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording = False
        self._listeners: list["queue.Queue"] = []
        self._stream = sd.InputStream(
            samplerate=_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            device=_DEVICE,
            callback=self._callback,
        )
        self._stream.start()

    def attach_listener(self, q: "queue.Queue") -> None:
        """Feed raw audio chunks to *q* for wake-word detection."""
        with self._lock:
            if q not in self._listeners:
                self._listeners.append(q)

    def detach_listener(self, q: "queue.Queue") -> None:
        with self._lock:
            try:
                self._listeners.remove(q)
            except ValueError:
                pass

    def _callback(self, indata, frames, time_info, status):
        chunk = indata[:, 0].copy()   # flatten to 1-D float32
        with self._lock:
            if self._recording:
                self._frames.append(indata.copy())
            for q in self._listeners:
                try:
                    q.put_nowait(chunk)
                except Exception:
                    pass

    def get_rms(self) -> float:
        """Return RMS of the most recent audio chunk (0.0 if nothing captured yet)."""
        with self._lock:
            if not self._frames:
                return 0.0
            return float(np.sqrt(np.mean(self._frames[-1] ** 2)))

    # ── hotkey path ───────────────────────────────────────────────────────────

    def start_recording(self):
        with self._lock:
            self._frames = []
        self._recording = True

    def close(self):
        self._recording = False
        self._stream.stop()
        self._stream.close()

    def stop_and_get(self) -> np.ndarray:
        self._recording = False
        with self._lock:
            if not self._frames:
                return np.zeros(0, dtype=np.float32)
            raw = np.concatenate(self._frames, axis=0).flatten()
        return _resample(raw, _RATE)

    # ── IPC path ──────────────────────────────────────────────────────────────

    def record_until_silence(
        self,
        max_seconds: float = 30,
        silence_threshold: float = 0.01,
        silence_duration: float = 1.5,
    ) -> np.ndarray:
        with self._lock:
            self._frames = []
        self._recording = True

        chunks_per_second = 10
        silence_chunks_needed = int(silence_duration * chunks_per_second)
        max_chunks = int(max_seconds * chunks_per_second)
        silence_chunks = 0

        for _ in range(max_chunks):
            time.sleep(1 / chunks_per_second)
            with self._lock:
                if not self._frames:
                    continue
                last_frame = self._frames[-1]
            rms = float(np.sqrt(np.mean(last_frame**2)))
            if rms < silence_threshold:
                silence_chunks += 1
            else:
                silence_chunks = 0
            if silence_chunks >= silence_chunks_needed:
                break

        self._recording = False
        with self._lock:
            if not self._frames:
                return np.zeros(0, dtype=np.float32)
            raw = np.concatenate(self._frames, axis=0).flatten()
        return _resample(raw, _RATE)
