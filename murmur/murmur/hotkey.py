from typing import Callable

from pynput import keyboard
from pynput.keyboard import Key


class HotkeyListener:
    def __init__(self, key_name: str, on_press: Callable, on_release: Callable):
        self._on_press_cb = on_press
        self._on_release_cb = on_release
        self._target_key = self._resolve_key(key_name)
        self._listener: keyboard.Listener | None = None

    def _resolve_key(self, key_name: str):
        # Try Key enum first (e.g. "F9" -> Key.f9)
        try:
            return Key[key_name.lower()]
        except KeyError:
            pass
        # Fall back to single character
        if len(key_name) == 1:
            return keyboard.KeyCode.from_char(key_name)
        return None

    def _on_press(self, key):
        if key == self._target_key:
            self._on_press_cb()

    def _on_release(self, key):
        if key == self._target_key:
            self._on_release_cb()

    def start(self):
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener is not None:
            self._listener.stop()
