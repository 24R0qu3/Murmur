import itertools
import signal
import threading
import time
from pathlib import Path

from .audio import AudioRecorder
from .config import load_config
from .hotkey import HotkeyListener
from .inject import inject_text
from .ipc import IPCServer
from .transcribe import Transcriber
from .tray import TrayIcon

_BAR_WIDTH = 24
_BAR_SCALE = 0.06
_SPINNER   = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _level_bar(rms: float) -> str:
    filled = int(min(rms / _BAR_SCALE, 1.0) * _BAR_WIDTH)
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


def _run_recording_display(stop: threading.Event, recorder: AudioRecorder):
    for spin in itertools.cycle(_SPINNER):
        if stop.is_set():
            break
        bar = _level_bar(recorder.get_rms())
        print(f"\r● {spin} [{bar}] recording … ", end="", flush=True)
        time.sleep(0.08)


def main():
    print("Loading model...")
    config      = load_config()
    transcriber = Transcriber(config)
    recorder    = AudioRecorder()
    _transcribe_lock = threading.Lock()

    print("Ready.")
    print()
    print(f"  {config.hotkey:<6}  hold to record, release to transcribe + inject")
    print(f"  language  {config.language}")
    print(f"  model     {config.model}")
    print(f"  Ctrl+C  exit")
    print()

    _anim         : dict              = {}
    _is_recording                     = threading.Event()
    _shutdown                         = threading.Event()
    _overlay                          = None   # OverlayWindow | None
    _root                             = None   # tk.Tk | None

    # ── Thread-safe helpers ───────────────────────────────────────────────────

    def _set_state(state: str):
        tray.set_state(state)
        if _root is not None and _overlay is not None:
            _root.after(0, lambda s=state: _overlay.set_state(s))

    def _push_transcription(text: str):
        tray.set_state("idle")
        if _root is not None and _overlay is not None:
            _root.after(0, lambda t=text: _overlay.add_transcription(t))

    # ── IPC handler ───────────────────────────────────────────────────────────

    def ipc_handler(cmd: dict) -> dict:
        command = cmd.get("cmd")
        if command == "status":
            return {"running": True}
        elif command == "listen":
            timeout          = cmd.get("timeout", 30)
            silence_duration = cmd.get("silence_duration", 1.5)
            countdown        = cmd.get("countdown", 0)
            if countdown > 0:
                for i in range(countdown, 0, -1):
                    print(f"\r  MCP  speak in {i}…   ", end="", flush=True)
                    time.sleep(1)
            print(
                f"\r  MCP ● speak now! (max {timeout}s, silence {silence_duration}s)   ",
                flush=True,
            )
            with _transcribe_lock:
                audio = recorder.record_until_silence(
                    max_seconds=timeout, silence_duration=silence_duration,
                )
                text = transcriber.transcribe(audio)
            print(
                f"\r  MCP → {text}{' ' * 10}" if text
                else f"\r  MCP   (nothing recognised){' ' * 10}"
            )
            return {"text": text}
        else:
            return {"error": f"Unknown command: {command!r}"}

    # ── Hotkey callbacks ──────────────────────────────────────────────────────

    def on_press():
        if _is_recording.is_set():
            return
        _is_recording.set()
        _set_state("recording")
        if _overlay is not None and _root is not None:
            _root.after(0, _overlay.raise_to_front)
        recorder.start_recording()
        stop = threading.Event()
        _anim["stop"] = stop
        threading.Thread(
            target=_run_recording_display, args=(stop, recorder), daemon=True,
        ).start()

    def _finish():
        stop = _anim.pop("stop", None)
        if stop:
            stop.set()
        _set_state("transcribing")
        print(f"\r◼  Transcribing …{' ' * (_BAR_WIDTH + 12)}", flush=True)
        with _transcribe_lock:
            audio = recorder.stop_and_get()
            try:
                text = transcriber.transcribe(audio)
            except Exception as e:
                err = str(e).lower()
                if "cublas" in err or "cuda" in err or "cublaslt" in err:
                    transcriber.switch_to_cpu()
                    try:
                        text = transcriber.transcribe(audio)
                    except Exception as e2:
                        print(f"\r  ERROR: {e2}{' ' * 10}")
                        _set_state("idle")
                        return
                else:
                    print(f"\r  ERROR: {e}{' ' * 10}")
                    _set_state("idle")
                    return
        if text:
            print(f"\r→  {text}{' ' * 10}")
            inject_text(text, delay_ms=config.inject_delay_ms)
            _push_transcription(text)
        else:
            print(f"\r   (nothing recognised){' ' * 10}")
            _set_state("idle")

    def on_release():
        if not _is_recording.is_set():
            return
        _is_recording.clear()
        threading.Thread(target=_finish, daemon=True).start()

    # ── IPC + hotkey ──────────────────────────────────────────────────────────

    ipc_server = IPCServer()
    ipc_server.start(ipc_handler)

    hotkey_listener = HotkeyListener(
        key_name=config.hotkey, on_press=on_press, on_release=on_release,
    )
    hotkey_listener.start()

    # ── Tray (started once, here) ─────────────────────────────────────────────

    config_path = Path.home() / ".config" / "murmur" / "config.toml"
    tray = TrayIcon(on_quit=_shutdown.set, config_path=config_path)
    if config.tray:
        tray.start()

    # ── Overlay + main loop ───────────────────────────────────────────────────

    if config.overlay:
        try:
            import tkinter as tk
            from .overlay import OverlayWindow
            from .settings_dialog import SettingsDialog

            _root = tk.Tk()

            def _apply_settings(**kw):
                nonlocal hotkey_listener
                config.language                = kw.get("language", config.language)
                config.overlay_raise_on_hotkey = kw.get("overlay_raise_on_hotkey",
                                                         config.overlay_raise_on_hotkey)
                transcriber._language          = config.language
                if _overlay is not None:
                    _overlay.apply_topmost(
                        kw.get("overlay_always_on_top", config.overlay_always_on_top)
                    )
                new_hotkey = kw.get("hotkey", config.hotkey)
                if new_hotkey != config.hotkey:
                    config.hotkey = new_hotkey
                    hotkey_listener.stop()
                    hotkey_listener = HotkeyListener(
                        key_name=config.hotkey, on_press=on_press, on_release=on_release,
                    )
                    hotkey_listener.start()

            def _save_position(x: int, y: int):
                config.overlay_x = x
                config.overlay_y = y
                try:
                    existing: dict = {}
                    if config_path.exists():
                        import tomllib
                        with open(config_path, "rb") as f:
                            existing = tomllib.load(f)
                    existing["overlay_x"] = x
                    existing["overlay_y"] = y
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    from .settings_dialog import _dump_toml
                    config_path.write_text(_dump_toml(existing))
                except Exception:
                    pass

            _settings_dialog = None

            def _open_settings():
                nonlocal _settings_dialog
                if _settings_dialog is not None and _settings_dialog.winfo_exists():
                    _settings_dialog.lift()
                    _settings_dialog.focus_force()
                    return
                _settings_dialog = SettingsDialog(_root, config, config_path, _apply_settings)

            # Let the tray open the dialog instead of the raw TOML file
            tray._on_settings = lambda: _root.after(0, _open_settings)

            _overlay = OverlayWindow(
                _root, config,
                on_settings=_open_settings,
                on_quit=_shutdown.set,
                get_rms=recorder.get_rms,
                on_move=_save_position,
            )

            # Route signals through tkinter thread to avoid race conditions
            signal.signal(signal.SIGINT,  lambda *_: _root.after(0, _shutdown.set))
            signal.signal(signal.SIGTERM, lambda *_: _root.after(0, _shutdown.set))

            def _check_shutdown():
                if _shutdown.is_set():
                    _root.quit()
                else:
                    _root.after(100, _check_shutdown)

            _root.after(100, _check_shutdown)
            _root.mainloop()

        except Exception as e:
            print(f"  overlay unavailable ({e}), running headless")
            signal.signal(signal.SIGINT,  lambda *_: _shutdown.set())
            signal.signal(signal.SIGTERM, lambda *_: _shutdown.set())
            while not _shutdown.is_set():
                _shutdown.wait(timeout=0.5)
    else:
        signal.signal(signal.SIGINT,  lambda *_: _shutdown.set())
        signal.signal(signal.SIGTERM, lambda *_: _shutdown.set())
        while not _shutdown.is_set():
            _shutdown.wait(timeout=0.5)

    # ── Shutdown ──────────────────────────────────────────────────────────────

    print("\nShutting down.")
    tray.stop()
    hotkey_listener.stop()
    recorder.close()


if __name__ == "__main__":
    main()
