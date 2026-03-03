"""
Wake-word detection via openwakeword (optional dependency).

Install:  uv run --extra wakeword murmur
          uv pip install openwakeword

Pre-trained models are English-only.  Custom/other-language phrases require
training with openwakeword's training pipeline.
"""

import queue
import threading
import time
from typing import Callable

_COOLDOWN_SECONDS = 2.0
_CHUNK_SAMPLES = 1280  # 80 ms at 16 kHz — openwakeword's expected chunk size


class WakeWordListener:
    """
    Listens to a raw-audio queue fed by AudioRecorder and fires a callback
    when the configured wake word is detected above the confidence threshold.
    """

    def __init__(self, model_name: str, threshold: float = 0.5):
        self._model_name = model_name
        self._threshold = threshold
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=50)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._paused = threading.Event()
        self._on_detected: Callable | None = None
        self._model = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, on_detected: Callable) -> bool:
        """Load model and start background detection thread.  Returns False if
        openwakeword is not installed."""
        try:
            from openwakeword.model import Model

            # Pass as a named built-in model or as a file path depending on the value
            name = self._model_name
            if (
                name.endswith(".onnx")
                or name.endswith(".tflite")
                or "/" in name
                or "\\" in name
            ):
                self._model = Model(wakeword_model_paths=[name])
            else:
                self._model = Model(wakeword_models=[name])
        except ModuleNotFoundError as e:
            if "openwakeword" in str(e):
                print(
                    "  Wake word unavailable: openwakeword is not installed.\n"
                    "  Run:  murmur --install-wakeword"
                )
            else:
                print(
                    f"  Wake word unavailable: missing dependency ({e}).\n"
                    "  Re-run:  murmur --install-wakeword"
                )
            return False
        except Exception as e:
            print(f"  Wake word unavailable: {e}")
            return False

        self._on_detected = on_detected
        self._stop_event.clear()
        self._paused.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f'  Wake word  "{self._model_name}"  (threshold {self._threshold})')
        return True

    def stop(self):
        self._stop_event.set()
        # Unblock the queue if it's waiting
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

    def pause(self):
        """Temporarily stop firing callbacks (e.g. during a recording)."""
        self._paused.set()

    def resume(self):
        """Re-enable callbacks after a pause."""
        self._paused.clear()
        # Drain stale audio that accumulated while paused
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    @property
    def queue(self) -> "queue.Queue[bytes]":
        """The audio queue — pass to AudioRecorder.attach_listener()."""
        return self._queue

    # ── Detection loop ────────────────────────────────────────────────────────

    def _run(self):
        import numpy as np

        from .audio import _RATE, _resample

        last_detection = 0.0
        buf = np.zeros(0, dtype=np.float32)

        while not self._stop_event.is_set():
            try:
                chunk = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if chunk is None:
                break

            if self._paused.is_set():
                continue

            # openwakeword requires 16 kHz; resample if the stream runs at a different rate
            chunk = _resample(chunk, _RATE)

            # Accumulate into _CHUNK_SAMPLES-sized windows
            buf = np.concatenate([buf, chunk])
            while len(buf) >= _CHUNK_SAMPLES:
                window = buf[:_CHUNK_SAMPLES]
                buf = buf[_CHUNK_SAMPLES:]

                try:
                    # openwakeword expects int16 PCM [-32768, 32767]
                    scores = self._model.predict((window * 32767).astype(np.int16))
                except Exception:
                    continue

                confidence = max(scores.get(k, 0.0) for k in scores)
                now = time.monotonic()
                if (
                    confidence >= self._threshold
                    and (now - last_detection) >= _COOLDOWN_SECONDS
                ):
                    last_detection = now
                    if self._on_detected and not self._paused.is_set():
                        self._on_detected()
