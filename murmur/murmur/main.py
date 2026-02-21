import itertools
import signal
import threading
import time

from .audio import AudioRecorder
from .config import load_config
from .hotkey import HotkeyListener
from .inject import inject_text
from .ipc import IPCServer
from .transcribe import Transcriber

_BAR_WIDTH = 24
_BAR_SCALE = 0.06   # RMS value that fills the bar completely
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _level_bar(rms: float) -> str:
    filled = int(min(rms / _BAR_SCALE, 1.0) * _BAR_WIDTH)
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


def _run_recording_display(stop: threading.Event, recorder: AudioRecorder):
    """Animate a live audio-level bar on one line until stop is set."""
    for spin in itertools.cycle(_SPINNER):
        if stop.is_set():
            break
        bar = _level_bar(recorder.get_rms())
        print(f"\r● {spin} [{bar}] recording … ", end="", flush=True)
        time.sleep(0.08)


def main():
    print("Loading model...")
    config = load_config()
    transcriber = Transcriber(config)
    recorder = AudioRecorder()
    _transcribe_lock = threading.Lock()
    print("Ready.")
    print()
    print(f"  {config.hotkey:<6}  hold to record, release to transcribe + inject")
    print(f"  language  {config.language}")
    print(f"  model     {config.model}")
    print(f"  Ctrl+C  exit")
    print()

    # Shared state between on_press / on_release
    _anim: dict = {}
    _is_recording = threading.Event()  # set while recording, guards against key-repeat

    def ipc_handler(cmd: dict) -> dict:
        command = cmd.get("cmd")
        if command == "status":
            return {"running": True}
        elif command == "listen":
            timeout = cmd.get("timeout", 30)
            silence_duration = cmd.get("silence_duration", 1.5)
            countdown = cmd.get("countdown", 0)
            if countdown > 0:
                for i in range(countdown, 0, -1):
                    print(f"\r  MCP  speak in {i}…   ", end="", flush=True)
                    time.sleep(1)
            print(f"\r  MCP ● speak now! (max {timeout}s, silence {silence_duration}s)   ", flush=True)
            with _transcribe_lock:
                audio = recorder.record_until_silence(max_seconds=timeout, silence_duration=silence_duration)
                text = transcriber.transcribe(audio)
            if text:
                print(f"\r  MCP → {text}{' ' * 10}")
            else:
                print(f"\r  MCP   (nothing recognised){' ' * 10}")
            return {"text": text}
        else:
            return {"error": f"Unknown command: {command!r}"}

    def on_press():
        if _is_recording.is_set():
            return  # ignore OS key-repeat events
        _is_recording.set()
        recorder.start_recording()
        stop = threading.Event()
        _anim["stop"] = stop
        threading.Thread(
            target=_run_recording_display, args=(stop, recorder), daemon=True
        ).start()

    def _finish():
        """Stop animation, transcribe, inject. Runs in a worker thread."""
        stop = _anim.pop("stop", None)
        if stop:
            stop.set()
        print(f"\r◼  Transcribing …{' ' * (_BAR_WIDTH + 12)}", flush=True)

        with _transcribe_lock:
            audio = recorder.stop_and_get()
            text = transcriber.transcribe(audio)

        if text:
            print(f"\r→  {text}{' ' * 10}")
            inject_text(text, delay_ms=config.inject_delay_ms)
        else:
            print(f"\r   (nothing recognised){' ' * 10}")

    def on_release():
        if not _is_recording.is_set():
            return
        _is_recording.clear()
        threading.Thread(target=_finish, daemon=True).start()

    ipc_server = IPCServer()
    ipc_server.start(ipc_handler)

    hotkey_listener = HotkeyListener(
        key_name=config.hotkey,
        on_press=on_press,
        on_release=on_release,
    )
    hotkey_listener.start()

    _shutdown = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: _shutdown.set())
    signal.signal(signal.SIGTERM, lambda *_: _shutdown.set())

    while not _shutdown.is_set():
        _shutdown.wait(timeout=0.5)

    print("\nShutting down.")
    hotkey_listener.stop()
    recorder.close()


if __name__ == "__main__":
    main()
