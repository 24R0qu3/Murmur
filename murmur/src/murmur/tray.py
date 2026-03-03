import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

try:
    import pystray
    from PIL import Image, ImageDraw

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_ICON_SIZE = 64

_COLORS = {
    "idle": (120, 120, 120, 255),  # grey
    "recording": (210, 50, 50, 255),  # red
    "transcribing": (210, 155, 30, 255),  # amber
}


def _make_image(color: tuple) -> "Image.Image":
    img = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    m = 8
    ImageDraw.Draw(img).ellipse([m, m, _ICON_SIZE - m, _ICON_SIZE - m], fill=color)
    return img


class TrayIcon:
    def __init__(self, on_quit: Callable, config_path: Path):
        self._on_quit = on_quit
        self._config_path = config_path
        self._on_settings: Callable | None = None
        self._icon = None
        self._state = "idle"

    def start(self) -> bool:
        """Start the tray icon in a daemon thread. Returns False if unavailable."""
        if not _AVAILABLE:
            return False
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Open Config", self._open_config),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            )
            self._icon = pystray.Icon(
                "murmur",
                _make_image(_COLORS["idle"]),
                "Murmur — idle",
                menu,
            )
            threading.Thread(target=self._run, daemon=True).start()
            return True
        except Exception:
            return False

    def _run(self):
        try:
            self._icon.run()
        except Exception:
            self._icon = None

    def set_state(self, state: str):
        if self._icon is None or state == self._state:
            return
        self._state = state
        self._icon.icon = _make_image(_COLORS.get(state, _COLORS["idle"]))
        self._icon.title = f"Murmur — {state}"

    def stop(self):
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass

    def _open_config(self):
        if self._on_settings is not None:
            self._on_settings()
            return
        # Fallback: open the raw TOML file
        path = self._config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text('model = "base"\nlanguage = "de"\nhotkey = "F9"\n')
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass

    def _quit(self):
        self._on_quit()
        self.stop()
