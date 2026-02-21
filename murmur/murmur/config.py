import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    model: str = "base"
    language: str = "de"
    hotkey: str = "F9"
    device: str = "auto"       # "auto" | "cpu" | "cuda"
    compute_type: str = "auto" # "auto" | "int8" | "int8_float32" | "float16" | "float32"
    inject_delay_ms: int = 0


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
        compute_type=data.get("compute_type", defaults.compute_type),
        inject_delay_ms=data.get("inject_delay_ms", defaults.inject_delay_ms),
    )
