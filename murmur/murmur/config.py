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
    )
