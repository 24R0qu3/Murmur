import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    model: str = "base"
    language: str = "de"
    hotkey: str = "F9"
    device: str = "cpu"
    inject_delay_ms: int = 0
    tray: bool = True
    overlay: bool = True
    overlay_always_on_top: bool = True
    overlay_raise_on_hotkey: bool = True
    overlay_x: int = -1
    overlay_y: int = -1


def load_config() -> Config:
    config_path = Path.home() / ".config" / "murmur" / "config.toml"
    defaults = Config()

    if not config_path.exists():
        return defaults

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    return Config(
        model=data.get("model", defaults.model),
        language=data.get("language", defaults.language),
        hotkey=data.get("hotkey", defaults.hotkey),
        device=data.get("device", defaults.device),
        inject_delay_ms=data.get("inject_delay_ms", defaults.inject_delay_ms),
        tray=data.get("tray", defaults.tray),
        overlay=data.get("overlay", defaults.overlay),
        overlay_always_on_top=data.get("overlay_always_on_top", defaults.overlay_always_on_top),
        overlay_raise_on_hotkey=data.get("overlay_raise_on_hotkey", defaults.overlay_raise_on_hotkey),
        overlay_x=data.get("overlay_x", defaults.overlay_x),
        overlay_y=data.get("overlay_y", defaults.overlay_y),
    )
