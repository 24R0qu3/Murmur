import logging
import sys
from unittest.mock import MagicMock

# Heavy/hardware backends are not importable on headless CI (pynput needs
# X11, sounddevice needs an audio stack, faster_whisper is a large ML
# runtime, pystray probes for a display backend at import time and raises
# Xlib.error.DisplayNameError rather than ImportError when none exists).
# The unit tests monkeypatch around them, so stub them here.
for _mod in (
    "sounddevice",
    "pynput",
    "pynput.keyboard",
    "faster_whisper",
    "pystray",
):
    sys.modules.setdefault(_mod, MagicMock())

# On a headless runner there is no input device, so opening an InputStream
# must fail — this mirrors real hardware-less machines and lets audio's
# device probe fall back to the native WHISPER_RATE (no resampling), which
# the recorder tests assume.
sys.modules["sounddevice"].InputStream.side_effect = OSError("no audio device")

logging.basicConfig(level=logging.DEBUG)
