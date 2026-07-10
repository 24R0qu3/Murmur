import logging
from pathlib import Path

import pytest

from murmur.log import setup

# ── Log setup tests ──────────────────────────────────────────────────────────


def test_root_logger_set_to_debug(tmp_path):
    log_path = str(tmp_path / "murmur.log")
    setup(log_path=log_path)
    assert logging.getLogger().level == logging.DEBUG


def test_console_handler_level(tmp_path):
    log_path = str(tmp_path / "murmur.log")
    console, _ = setup(console_level="INFO", log_path=log_path)
    assert console.level == logging.INFO


def test_file_handler_level(tmp_path):
    log_path = str(tmp_path / "murmur.log")
    _, file = setup(file_level="WARNING", log_path=log_path)
    assert file.level == logging.WARNING


def test_log_file_created(tmp_path):
    log_path = str(tmp_path / "murmur.log")
    setup(log_path=log_path)
    assert Path(log_path).exists()


def test_log_dir_created(tmp_path):
    log_path = str(tmp_path / "subdir" / "murmur.log")
    setup(log_path=log_path)
    assert Path(log_path).parent.is_dir()


# ── CLI arg parsing tests ─────────────────────────────────────────────────────

_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


def _make_parser():
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--log", default="WARNING", choices=_LEVELS)
    parser.add_argument("--log-file", default="DEBUG", choices=_LEVELS)
    parser.add_argument("--log-path", default=None)
    return parser


@pytest.mark.parametrize(
    "flag,expected",
    [
        ([], "WARNING"),
        (["--log", "DEBUG"], "DEBUG"),
        (["--log", "INFO"], "INFO"),
    ],
)
def test_log_flag(flag, expected):
    args, _ = _make_parser().parse_known_args(flag)
    assert args.log == expected


def test_custom_log_path(tmp_path):
    log_path = str(tmp_path / "custom.log")
    args, _ = _make_parser().parse_known_args(["--log-path", log_path])
    assert args.log_path == log_path


# ── Config: hotkey watchdog cap (FIX 2) ───────────────────────────────────────


def test_max_record_seconds_default():
    from murmur.config import Config

    assert Config().max_record_seconds == 120


def test_max_record_seconds_from_toml(tmp_path, monkeypatch):
    from pathlib import Path

    import murmur.config as config_mod

    config_path = tmp_path / ".config" / "murmur" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("max_record_seconds = 45\n")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert config_mod.load_config().max_record_seconds == 45


# ── AudioRecorder generation-safety (FIX 3) ───────────────────────────────────


def _bare_recorder():
    """An AudioRecorder without opening a real InputStream (no audio hardware)."""
    import threading

    from murmur.audio import AudioRecorder

    r = AudioRecorder.__new__(AudioRecorder)
    r._frames = []
    r._lock = threading.Lock()
    r._recording = False
    r._generation = 0
    r._listeners = []
    return r


def test_stop_and_get_returns_frames_for_current_generation():
    import numpy as np

    r = _bare_recorder()
    gen = r.start_recording()
    r._frames.append(np.ones((10, 1), dtype=np.float32))
    audio = r.stop_and_get(gen)
    assert audio.size == 10
    assert r._recording is False


def test_stale_stop_does_not_kill_newer_recording():
    """A late finisher from an earlier hold must not stop a newer recording."""
    import numpy as np

    r = _bare_recorder()
    gen1 = r.start_recording()
    r._frames.append(np.ones((10, 1), dtype=np.float32))

    # User re-presses quickly: a new recording begins (frames cleared, new gen).
    gen2 = r.start_recording()
    assert gen2 != gen1
    r._frames.append(np.ones((8, 1), dtype=np.float32))

    # The still-pending first finisher now runs — it must be a no-op.
    stale = r.stop_and_get(gen1)
    assert stale.size == 0
    assert r._recording is True  # the new recording is left running

    # The new recording still finishes normally and keeps its own audio.
    fresh = r.stop_and_get(gen2)
    assert fresh.size == 8
    assert r._recording is False


# ── Guarded text injection (FIX 1) ────────────────────────────────────────────


def test_inject_guarded_missing_tool_x11(monkeypatch, capsys):
    import murmur.main as main_mod

    def _boom(*a, **k):
        raise FileNotFoundError("xdotool")

    monkeypatch.setattr(main_mod, "inject_text", _boom)
    monkeypatch.setattr(main_mod, "detect_platform", lambda: "x11")

    # Must not raise — the daemon thread has to survive a missing binary.
    main_mod._inject_guarded("hello", 0)
    out = capsys.readouterr().out
    assert "xdotool not found" in out
    assert "sudo apt install xdotool" in out


def test_inject_guarded_missing_tool_wayland(monkeypatch, capsys):
    import murmur.main as main_mod

    def _boom(*a, **k):
        raise FileNotFoundError("ydotool")

    monkeypatch.setattr(main_mod, "inject_text", _boom)
    monkeypatch.setattr(main_mod, "detect_platform", lambda: "wayland")

    main_mod._inject_guarded("hello", 0)
    out = capsys.readouterr().out
    assert "ydotool not found" in out
    assert "sudo apt install ydotool" in out


def test_inject_guarded_nonzero_exit(monkeypatch, capsys):
    import subprocess

    import murmur.main as main_mod

    def _boom(*a, **k):
        raise subprocess.CalledProcessError(3, ["xdotool"])

    monkeypatch.setattr(main_mod, "inject_text", _boom)
    monkeypatch.setattr(main_mod, "detect_platform", lambda: "x11")

    main_mod._inject_guarded("hello", 0)
    out = capsys.readouterr().out
    assert "text injection failed (xdotool exited 3)" in out


def test_inject_guarded_success_is_silent(monkeypatch, capsys):
    import murmur.main as main_mod

    calls = {}

    def _ok(text, delay_ms=0):
        calls["text"] = text

    monkeypatch.setattr(main_mod, "inject_text", _ok)
    monkeypatch.setattr(main_mod, "detect_platform", lambda: "x11")

    main_mod._inject_guarded("hello", 0)
    assert calls["text"] == "hello"
    assert "ERROR" not in capsys.readouterr().out
