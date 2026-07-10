import argparse
import itertools
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .audio import AudioRecorder
from .config import load_config
from .cuda_installer import install_cuda
from .hotkey import HotkeyListener
from .inject import detect_platform, inject_text
from .ipc import IPCServer
from .log import setup as _log_setup
from .transcribe import Transcriber
from .tray import TrayIcon
from .wakeword_installer import inject_wakeword_path, install_wakeword

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]

_BAR_WIDTH = 24
_BAR_SCALE = 0.06
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _level_bar(rms: float) -> str:
    filled = int(min(rms / _BAR_SCALE, 1.0) * _BAR_WIDTH)
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


def _inject_guarded(text: str, delay_ms: int) -> None:
    """Inject *text*, surviving a missing or failing injection tool.

    Never raises: the daemon thread that calls this must not die on a missing
    xdotool/ydotool binary (``FileNotFoundError``) or a non-zero exit
    (``CalledProcessError``), which would lose the text and leave the UI stuck.
    """
    tool = "ydotool" if detect_platform() == "wayland" else "xdotool"
    try:
        inject_text(text, delay_ms=delay_ms)
    except FileNotFoundError:
        print(
            f"\r  ERROR: {tool} not found — install it with: "
            f"sudo apt install {tool}{' ' * 10}"
        )
    except subprocess.CalledProcessError as e:
        print(
            f"\r  ERROR: text injection failed ({tool} exited {e.returncode})"
            f"{' ' * 10}"
        )
    except Exception as e:  # last resort — keep the daemon thread alive
        print(f"\r  ERROR: text injection failed ({e}){' ' * 10}")


def _run_recording_display(stop: threading.Event, recorder: AudioRecorder):
    for spin in itertools.cycle(_SPINNER):
        if stop.is_set():
            break
        bar = _level_bar(recorder.get_rms())
        print(f"\r● {spin} [{bar}] recording … ", end="", flush=True)
        time.sleep(0.08)


def _uninstall() -> int:
    from platformdirs import user_data_dir, user_log_dir

    removed = []

    # Side-installs: wakeword and cuda venvs + model downloads
    data_dir = Path(user_data_dir("murmur", appauthor=False))
    if data_dir.exists():
        shutil.rmtree(data_dir)
        removed.append(str(data_dir))

    # Config
    config_dir = Path.home() / ".config" / "murmur"
    if config_dir.exists():
        shutil.rmtree(config_dir)
        removed.append(str(config_dir))

    # Logs (platformdirs puts these separately on some platforms)
    log_dir = Path(user_log_dir("murmur", appauthor=False))
    if log_dir.exists() and log_dir != data_dir:
        shutil.rmtree(log_dir)
        removed.append(str(log_dir))

    if removed:
        print("  Removed:")
        for p in removed:
            print(f"    {p}")
    else:
        print("  Nothing to remove.")

    # The binary can't delete itself while running — print manual step
    if sys.platform == "win32":
        print(
            "\n  To remove the binary:\n"
            '    Remove-Item "$env:LOCALAPPDATA\\Programs\\murmur" -Recurse -Force'
        )
    else:
        print("\n  To remove the binary:\n    rm ~/.local/bin/murmur")

    return 0


def _start_mcp_mode():
    import socket as _socket
    import subprocess
    import time

    if sys.platform == "win32":

        def _daemon_running() -> bool:
            try:
                import win32file

                handle = win32file.CreateFile(
                    r"\\.\pipe\murmur",
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None,
                )
                win32file.CloseHandle(handle)
                return True
            except Exception:
                return False
    else:

        def _daemon_running() -> bool:
            try:
                with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    s.connect("/tmp/murmur.sock")
                    return True
            except OSError:
                return False

    if not _daemon_running():
        print("Starting Murmur daemon in background…", flush=True)
        subprocess.Popen(
            [sys.argv[0], "--headless"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(30):
            time.sleep(0.5)
            if _daemon_running():
                break
        else:
            print("ERROR: Murmur daemon did not start in time.", file=sys.stderr)
            sys.exit(1)

    from murmur_mcp.main import main as mcp_main

    print("Murmur daemon ready.", file=sys.stderr, flush=True)
    mcp_main()


def main():
    import os as _os

    # Suppress noisy GTK system warnings that are harmless but confusing to users.
    # These come from system plugins (IBus, gvfs, xapp) with GLib version mismatches.
    _os.environ.setdefault("GTK_MODULES", "")  # skip xapp-gtk3-module etc.
    _os.environ.setdefault("GTK_IM_MODULE", "gtk-im-context-simple")  # skip IBus IM
    _os.environ.setdefault("GIO_USE_VFS", "local")  # skip gvfs/dbus VFS plugin
    _os.environ.setdefault("NO_AT_BRIDGE", "1")  # skip atk-bridge accessibility

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--log", default="WARNING", choices=LEVELS)
    parser.add_argument("--log-file", default="DEBUG", choices=LEVELS)
    parser.add_argument("--log-path", default=None)
    parser.add_argument(
        "--install-wakeword",
        action="store_true",
        help="Install the optional openwakeword package and exit.",
    )
    parser.add_argument(
        "--install-cuda",
        action="store_true",
        help="Install CUDA runtime libraries for GPU acceleration and exit.",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove all murmur data (wakeword, cuda, logs) and exit.",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Start the MCP server (auto-starts the daemon in background if not running).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run daemon without overlay or tray icon (used when auto-started by --mcp).",
    )
    args, _ = parser.parse_known_args()

    # Install wake word support and exit if requested
    if args.install_wakeword:
        raise SystemExit(install_wakeword())

    if args.install_cuda:
        raise SystemExit(install_cuda())

    if args.uninstall:
        raise SystemExit(_uninstall())

    if args.mcp:
        _start_mcp_mode()
        return

    # Inject side-installed wakeword path before any imports that need it
    inject_wakeword_path()

    kw = {"console_level": args.log, "file_level": args.log_file}
    if args.log_path:
        kw["log_path"] = args.log_path
    _log_setup(**kw)

    print("Loading model...")
    config = load_config()
    if args.headless:
        config.overlay = False
        config.tray = False
    transcriber = Transcriber(config)
    recorder = AudioRecorder()
    _transcribe_lock = threading.Lock()

    from murmur import __version__

    print(f"Murmur v{__version__} — ready.")
    print()
    device_label = transcriber.device
    if transcriber._auto_detected:
        device_label += "  (auto-detected)"
    print(f"  {config.hotkey:<6}  hold to record, release to transcribe + inject")
    print(f"  language  {config.language}")
    print(f"  model     {config.model}")
    print(f"  device    {device_label}")
    print(f"  compute   {transcriber.compute_type}")
    if config.wake_word:
        print(f'  wake word "{config.wake_word}"')
    print("  Ctrl+C  exit")
    print()

    _anim: dict = {}
    _is_recording = threading.Event()
    # Guards the record start/stop transition so a watchdog auto-stop and a real
    # key-release can never both finish the same hold (no double-finish), and so
    # start_recording()/its generation are set atomically with _is_recording.
    _state_lock = threading.Lock()
    _record_gen = {"id": 0}  # generation id of the active hotkey recording
    _record_ended = {"ev": None}  # Event that wakes the watchdog when done
    _shutdown = threading.Event()
    _overlay = None  # OverlayWindow | None
    _wakeword_listener = None  # WakeWordListener | None

    # ── Thread-safe helpers ───────────────────────────────────────────────────

    def _set_state(state: str):
        import wx

        tray.set_state(state)
        if _overlay is not None:
            wx.CallAfter(_overlay.set_state, state)

    def _push_transcription(text: str):
        import wx

        tray.set_state("idle")
        if _overlay is not None:
            wx.CallAfter(_overlay.add_transcription, text)

    # ── IPC handler ───────────────────────────────────────────────────────────

    def ipc_handler(cmd: dict) -> dict:
        nonlocal hotkey_listener, _wakeword_listener
        command = cmd.get("cmd")
        if command == "status":
            return {"running": True}
        elif command == "get_config":
            return {
                "model": config.model,
                "language": config.language,
                "hotkey": config.hotkey,
                "device": config.device,
                "compute_type": config.compute_type,
                "wake_word": config.wake_word,
                "wake_word_threshold": config.wake_word_threshold,
                "inject_delay_ms": config.inject_delay_ms,
            }
        elif command == "configure":
            setting = cmd.get("setting")
            value = cmd.get("value")
            VALID = {
                "language",
                "model",
                "device",
                "compute_type",
                "hotkey",
                "wake_word",
                "wake_word_threshold",
                "inject_delay_ms",
            }
            REQUIRES_RESTART = {"model", "device", "compute_type"}
            if setting not in VALID:
                return {
                    "error": f"Unknown setting: {setting!r}. Valid: {sorted(VALID)}"
                }
            if setting == "language":
                config.language = str(value)
                transcriber._language = str(value)
            elif setting == "inject_delay_ms":
                config.inject_delay_ms = int(value)
            elif setting == "wake_word_threshold":
                config.wake_word_threshold = float(value)
            elif setting == "hotkey":
                config.hotkey = str(value)
                hotkey_listener.stop()
                hotkey_listener = HotkeyListener(
                    key_name=config.hotkey,
                    on_press=on_press,
                    on_release=on_release,
                )
                hotkey_listener.start()
            elif setting == "wake_word":
                config.wake_word = str(value)
                if _wakeword_listener:
                    recorder.detach_listener(_wakeword_listener.queue)
                    _wakeword_listener.stop()
                    _wakeword_listener = None
                if value:
                    from .wakeword import WakeWordListener

                    _wakeword_listener = WakeWordListener(
                        model_name=config.wake_word,
                        threshold=config.wake_word_threshold,
                    )
                    _wakeword_listener.start(_on_wake_word)
                    recorder.attach_listener(_wakeword_listener.queue)
            else:
                setattr(config, setting, value)
            try:
                existing: dict = {}
                if config_path.exists():
                    import tomllib

                    with open(config_path, "rb") as f:
                        existing = tomllib.load(f)
                existing[setting] = value
                config_path.parent.mkdir(parents=True, exist_ok=True)
                from .settings_dialog import _dump_toml

                config_path.write_text(_dump_toml(existing))
            except Exception:
                pass
            result: dict = {"ok": True}
            if setting in REQUIRES_RESTART:
                result["note"] = (
                    f"Restart Murmur for the {setting!r} change to take effect."
                )
            return result
        elif command == "listen":
            timeout = cmd.get("timeout", 30)
            silence_duration = cmd.get("silence_duration", 1.5)
            countdown = cmd.get("countdown", 0)
            if countdown > 0:
                for i in range(countdown, 0, -1):
                    print(f"\r  MCP  speak in {i}…   ", end="", flush=True)
                    time.sleep(1)
            print(
                f"\r  MCP ● speak now! (max {timeout}s, silence {silence_duration}s)   ",
                flush=True,
            )
            if _wakeword_listener:
                _wakeword_listener.pause()
            with _transcribe_lock:
                audio = recorder.record_until_silence(
                    max_seconds=timeout,
                    silence_duration=silence_duration,
                )
                text = transcriber.transcribe(audio)
            if _wakeword_listener:
                _wakeword_listener.resume()
            print(
                f"\r  MCP → {text}{' ' * 10}"
                if text
                else f"\r  MCP   (nothing recognised){' ' * 10}"
            )
            return {"text": text}
        else:
            return {"error": f"Unknown command: {command!r}"}

    # ── Hotkey callbacks ──────────────────────────────────────────────────────

    def on_press(start_watchdog: bool = True):
        with _state_lock:
            if _is_recording.is_set():
                return
            _is_recording.set()
            gen = recorder.start_recording()
            _record_gen["id"] = gen
            ended = threading.Event()
            _record_ended["ev"] = ended
        _set_state("recording")
        if _overlay is not None:
            import wx

            wx.CallAfter(_overlay.raise_to_front)
        stop = threading.Event()
        _anim["stop"] = stop
        threading.Thread(
            target=_run_recording_display,
            args=(stop, recorder),
            daemon=True,
        ).start()
        if start_watchdog:
            threading.Thread(
                target=_record_watchdog,
                args=(gen, ended),
                daemon=True,
            ).start()

    def _claim_finish(gen: int) -> bool:
        """Atomically claim the finish for generation *gen*.

        Returns True only for the single caller (key-release *or* watchdog)
        that transitions the hold out of recording; every other caller,
        including the stale key-release after a watchdog auto-stop, gets False.
        """
        with _state_lock:
            if not _is_recording.is_set() or _record_gen["id"] != gen:
                return False
            _is_recording.clear()
            return True

    def _record_watchdog(gen: int, ended: threading.Event):
        # Wake early when the hold ends normally; otherwise fire after the cap.
        if ended.wait(timeout=config.max_record_seconds):
            return
        if not _claim_finish(gen):
            return
        print(
            f"\r  Recording auto-stopped after {config.max_record_seconds}s"
            f"{' ' * 10}",
            flush=True,
        )
        _finish(gen)

    def _finish(gen: int):
        stop = _anim.pop("stop", None)
        if stop:
            stop.set()
        _set_state("transcribing")
        print(f"\r◼  Transcribing …{' ' * (_BAR_WIDTH + 12)}", flush=True)
        with _transcribe_lock:
            audio = recorder.stop_and_get(gen)
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
            # Always land back on idle and keep the text in the overlay history,
            # even if injection fails — _inject_guarded never raises, and the
            # finally guarantees the UI is never left stuck on "transcribing".
            try:
                _inject_guarded(text, config.inject_delay_ms)
            finally:
                _push_transcription(text)
        else:
            print(f"\r   (nothing recognised){' ' * 10}")
            _set_state("idle")

    def on_release():
        gen = _record_gen["id"]
        if not _claim_finish(gen):
            return
        ended = _record_ended.get("ev")
        if ended is not None:
            ended.set()  # wake the watchdog so it exits instead of firing later
        threading.Thread(target=_finish, args=(gen,), daemon=True).start()

    # ── IPC + hotkey ──────────────────────────────────────────────────────────

    ipc_server = IPCServer()
    ipc_server.start(ipc_handler)

    hotkey_listener = HotkeyListener(
        key_name=config.hotkey,
        on_press=on_press,
        on_release=on_release,
    )
    hotkey_listener.start()

    # ── Wake word callbacks (always defined so _apply_settings can reference them)

    def _on_wake_word():
        if not _is_recording.is_set():
            print("\n  Hello! Wake word detected — recording…", flush=True)
            # No hotkey watchdog here: record_until_silence() already caps the
            # wake-word recording via its own max_seconds.
            on_press(start_watchdog=False)
            threading.Thread(target=_wake_word_finish, daemon=True).start()

    def _wake_word_finish():
        with _transcribe_lock:
            audio = recorder.record_until_silence(
                max_seconds=30,
                silence_duration=5.0,
            )
            # Stop the spinner animation started by on_press()
            stop = _anim.pop("stop", None)
            if stop:
                stop.set()
            _set_state("transcribing")
            print(f"\r◼  Transcribing …{' ' * (_BAR_WIDTH + 12)}", flush=True)
            try:
                text = transcriber.transcribe(audio)
            except Exception as e:
                print(f"\r  ERROR: {e}{' ' * 10}")
                _set_state("idle")
                _is_recording.clear()
                return
        _is_recording.clear()
        ended = _record_ended.get("ev")
        if ended is not None:
            ended.set()
        if text:
            print(f"\r→  {text}{' ' * 10}")
            try:
                _inject_guarded(text, config.inject_delay_ms)
            finally:
                _push_transcription(text)
        else:
            print(f"\r   (nothing recognised){' ' * 10}")
            _set_state("idle")

    # ── Wake word initial start (optional) ────────────────────────────────────

    if config.wake_word:
        from .wakeword import WakeWordListener

        _wakeword_listener = WakeWordListener(
            model_name=config.wake_word,
            threshold=config.wake_word_threshold,
        )
        _wakeword_listener.start(_on_wake_word)
        recorder.attach_listener(_wakeword_listener.queue)

    # ── Tray (started once, here) ─────────────────────────────────────────────

    config_path = Path.home() / ".config" / "murmur" / "config.toml"
    tray = TrayIcon(on_quit=_shutdown.set, config_path=config_path)
    if config.tray:
        tray.start()

    # ── Overlay + main loop ───────────────────────────────────────────────────

    if config.overlay:
        try:
            import wx

            from .overlay import OverlayWindow
            from .settings_dialog import SettingsDialog

            app = wx.App(False)

            def _apply_settings(**kw):
                nonlocal hotkey_listener, _wakeword_listener
                config.language = kw.get("language", config.language)
                config.overlay_raise_on_hotkey = kw.get(
                    "overlay_raise_on_hotkey", config.overlay_raise_on_hotkey
                )
                transcriber._language = config.language
                if _overlay is not None:
                    _overlay.apply_topmost(
                        kw.get("overlay_always_on_top", config.overlay_always_on_top)
                    )
                new_hotkey = kw.get("hotkey", config.hotkey)
                if new_hotkey != config.hotkey:
                    config.hotkey = new_hotkey
                    hotkey_listener.stop()
                    hotkey_listener = HotkeyListener(
                        key_name=config.hotkey,
                        on_press=on_press,
                        on_release=on_release,
                    )
                    hotkey_listener.start()
                new_wake_word = kw.get("wake_word", config.wake_word)
                new_threshold = kw.get(
                    "wake_word_threshold", config.wake_word_threshold
                )
                if (
                    new_wake_word != config.wake_word
                    or new_threshold != config.wake_word_threshold
                ):
                    config.wake_word = new_wake_word
                    config.wake_word_threshold = new_threshold
                    if _wakeword_listener:
                        recorder.detach_listener(_wakeword_listener.queue)
                        _wakeword_listener.stop()
                        _wakeword_listener = None
                    if new_wake_word:
                        from .wakeword import WakeWordListener

                        _wakeword_listener = WakeWordListener(
                            model_name=new_wake_word,
                            threshold=new_threshold,
                        )
                        _wakeword_listener.start(_on_wake_word)
                        recorder.attach_listener(_wakeword_listener.queue)

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
                if _settings_dialog is not None:
                    try:
                        _settings_dialog.Raise()
                        _settings_dialog.SetFocus()
                        return
                    except RuntimeError:
                        pass
                _settings_dialog = SettingsDialog(
                    _overlay,
                    config,
                    config_path,
                    _apply_settings,
                    on_recenter=_overlay.recenter,
                )
                _settings_dialog.Show()

            # Let the tray open the dialog instead of the raw TOML file
            tray._on_settings = lambda: wx.CallAfter(_open_settings)

            _overlay = OverlayWindow(
                config,
                on_settings=_open_settings,
                on_quit=_shutdown.set,
                get_rms=recorder.get_rms,
                on_move=_save_position,
            )

            # Route signals through wx main loop
            signal.signal(signal.SIGINT, lambda *_: wx.CallAfter(_shutdown.set))
            signal.signal(signal.SIGTERM, lambda *_: wx.CallAfter(_shutdown.set))

            def _check_shutdown():
                if _shutdown.is_set():
                    app.ExitMainLoop()
                else:
                    wx.CallLater(100, _check_shutdown)

            wx.CallLater(100, _check_shutdown)
            app.MainLoop()

        except Exception as e:
            print(f"  overlay unavailable ({e}), running headless")
            signal.signal(signal.SIGINT, lambda *_: _shutdown.set())
            signal.signal(signal.SIGTERM, lambda *_: _shutdown.set())
            while not _shutdown.is_set():
                _shutdown.wait(timeout=0.5)
    else:
        signal.signal(signal.SIGINT, lambda *_: _shutdown.set())
        signal.signal(signal.SIGTERM, lambda *_: _shutdown.set())
        while not _shutdown.is_set():
            _shutdown.wait(timeout=0.5)

    # ── Shutdown ──────────────────────────────────────────────────────────────

    print("\nShutting down.")
    if _wakeword_listener:
        recorder.detach_listener(_wakeword_listener.queue)
        _wakeword_listener.stop()
    tray.stop()
    hotkey_listener.stop()
    recorder.close()


if __name__ == "__main__":
    main()
