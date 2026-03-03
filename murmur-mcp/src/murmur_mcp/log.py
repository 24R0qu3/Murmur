import logging
import logging.handlers
from pathlib import Path

from platformdirs import user_log_dir


def setup(
    console_level: str = "WARNING",
    file_level: str = "DEBUG",
    log_path: str = str(
        Path(user_log_dir("murmur-mcp", appauthor=False)) / "murmur-mcp.log"
    ),
    max_bytes: int = 1_000_000,
    backup_count: int = 3,
):
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, console_level.upper(), logging.WARNING))
    console.setFormatter(formatter)
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    file = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    file.setLevel(getattr(logging, file_level.upper(), logging.DEBUG))
    file.setFormatter(formatter)
    root.addHandler(console)
    root.addHandler(file)
    return console, file
