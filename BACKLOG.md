# Murmur Backlog

---

## Feature 7: GUI Tray Icon

**Goal / User Story**

As a developer running Murmur in the background, I want a system tray icon that shows at a glance whether Murmur is idle, recording, or transcribing — and that lets me toggle the daemon, change the hotkey, switch models, and quit without touching a terminal.

**Suggested Library / Approach**

Use `pystray` (cross-platform: Windows, Linux, macOS) for the tray icon and menu.
Use `Pillow` to generate simple coloured icon images programmatically (no external icon files required).

Tray states:

| State | Icon colour | When |
|---|---|---|
| Idle / Ready | Grey | Daemon running, waiting for F9 |
| Recording | Red | Inside `on_press()` |
| Transcribing | Yellow/Amber | Inside `_finish()` between stop and inject |

**Key Implementation Steps**

1. Create `murmur/murmur/tray.py` — a `TrayIcon` class wrapping `pystray.Icon`.
   - Accepts callbacks: `on_quit`, `on_open_config`, `on_reload`.
   - Exposes `set_state(state: str)` to swap the icon image.
   - Use `pystray.Icon.run_detached()` to keep it non-blocking.
   - Build icon images with Pillow: filled circle on 64×64 transparent canvas.

2. In `main.py`:
   - Instantiate `TrayIcon` after model load, call `run_detached()`.
   - `tray.set_state("recording")` in `on_press()`.
   - `tray.set_state("transcribing")` at top of `_finish()`.
   - `tray.set_state("idle")` at bottom of `_finish()`.
   - Wire "Quit" to `_shutdown.set()`.
   - Wire "Open config" to `os.startfile` (Windows) / `xdg-open` (Linux).
   - Wire "Reload config" to re-call `load_config()` (note: model changes require restart).

3. Add `pystray` and `Pillow` to `murmur/pyproject.toml`.

4. Add `tray: bool = True` to `config.py` — set `false` for headless/server use.

**Files to Create or Modify**

- `murmur/murmur/tray.py` — **new**
- `murmur/murmur/main.py`
- `murmur/murmur/config.py`
- `murmur/pyproject.toml`

**Risks / Open Questions**

- Linux requires `libayatana-appindicator3` (system package, not pip). Document or gracefully degrade.
- `pystray` on macOS requires main-thread execution — not a concern for Windows/Linux targets.
- Hot-reloading a new model is slow; show a dialog "Restart to apply model changes" instead.

---

## Feature 8: Wake Word

**Goal / User Story**

As a developer, I want to say a configurable trigger phrase (e.g. "hey murmur") to start recording without reaching for a hotkey. Silence after speech ends the recording and triggers transcription+injection — the same path as hotkey release.

**Suggested Library / Approach**

Use `openwakeword` (Apache 2.0, fully local, CPU-only, no API key). Processes a continuous audio stream in 80 ms chunks, fires a callback when confidence exceeds a threshold.

Add as an **optional** dependency — users opt in with `uv run --extra wakeword murmur`.

**Key Implementation Steps**

1. Create `murmur/murmur/wakeword.py` — `WakeWordListener` class.
   - Loads `openwakeword.Model(wakeword_models=[model_name])`.
   - `start(on_detected)` / `stop()` / `pause()` / `resume()` methods.
   - Background thread reads from a `queue.Queue`, calls `model.predict(chunk)`, fires `on_detected()` on threshold hit, enters 2s cooldown.

2. In `audio.py`, add audio fan-out to `AudioRecorder`:
   - `attach_listener(q: Queue)` / `detach_listener(q: Queue)`.
   - `_callback` pushes raw chunks to all attached queues (under `self._lock`).
   - Cap queue at `maxsize=50` (≈4s of audio) to prevent unbounded growth.

3. In `main.py`:
   - Instantiate `WakeWordListener` only when `config.wake_word` is non-empty.
   - Wire `on_detected` → `on_press()`.
   - After detection, use `record_until_silence` path (same as IPC), then call `_finish()`.
   - Pause wake-word listener during IPC-triggered recordings.

4. New config fields in `config.py`:
   - `wake_word: str = ""` — empty disables the feature
   - `wake_word_threshold: float = 0.5`

5. In `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   wakeword = ["openwakeword"]
   ```

**Files to Create or Modify**

- `murmur/murmur/wakeword.py` — **new**
- `murmur/murmur/audio.py`
- `murmur/murmur/config.py`
- `murmur/murmur/main.py`
- `murmur/pyproject.toml`

**Risks / Open Questions**

- Pre-trained models are English-only. Custom/German phrases require training with `openwakeword`'s pipeline. Document prominently.
- False positives: expose `wake_word_threshold` in config. Default 0.5 is a starting point.
- Detection latency ~160–300 ms after phrase ends — acceptable.
- Must not conflict with concurrent IPC `listen` sessions — use `pause()`/`resume()`.

---

## Feature 10: GPU Auto-detect

**Goal / User Story**

As a developer with an NVIDIA GPU, I want Murmur to automatically use CUDA without editing `config.toml`. On machines without a GPU it must silently fall back to CPU.

**Suggested Library / Approach**

`ctranslate2` (already a transitive dependency of `faster-whisper`) exposes `get_cuda_device_count()`. No new dependencies needed.

Respect explicit `device = "cpu"` or `device = "cuda"` in config — auto-detect only when `device = "auto"` (new default).

**Key Implementation Steps**

1. Add `detect_device()` to `transcribe.py`:
   ```python
   def detect_device() -> str:
       try:
           import ctranslate2
           if ctranslate2.get_cuda_device_count() > 0:
               return "cuda"
       except Exception:
           pass
       return "cpu"
   ```

2. In `config.py`, change default: `device: str = "auto"`.

3. In `transcribe.py`, resolve device before passing to `WhisperModel`:
   ```python
   def _resolve_device(requested: str) -> str:
       return detect_device() if requested == "auto" else requested
   ```
   Expose `self.device` on `Transcriber` for display in startup output.

4. Also auto-select `compute_type`: `"float16"` on CUDA, `"int8_float32"` on CPU.
   Add `compute_type: str = "auto"` config field.

5. In `main.py`, print resolved device in startup:
   ```
     device    cuda  (auto-detected)
   ```

**Files to Create or Modify**

- `murmur/murmur/transcribe.py`
- `murmur/murmur/config.py`
- `murmur/murmur/main.py`

**Risks / Open Questions**

- CPU-only `ctranslate2` builds raise `RuntimeError` from `get_cuda_device_count()` — handled by `try/except`.
- VRAM exhaustion with large models: catch errors in `transcribe()` and suggest `device = "cpu"` or a smaller model.
- CUDA DLLs must be on `PATH` (standard with NVIDIA driver install) — document in README troubleshooting.
