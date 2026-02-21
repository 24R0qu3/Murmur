import os
import subprocess
import sys


def detect_platform() -> str:
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    if sys.platform == "win32":
        return "windows"
    return "x11"  # fallback for headless Linux


def inject_text(text: str, delay_ms: int = 0):
    if delay_ms > 0:
        import time
        time.sleep(delay_ms / 1000)

    platform = detect_platform()

    if platform == "x11":
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", "0", text],
            check=True,
        )
    elif platform == "wayland":
        subprocess.run(["ydotool", "type", text], check=True)
    elif platform == "windows":
        import pyautogui
        import pyperclip

        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
