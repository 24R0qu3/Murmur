import logging
from pathlib import Path

from murmur_mcp.log import setup

# ── Log setup tests ──────────────────────────────────────────────────────────


def test_root_logger_set_to_debug(tmp_path):
    log_path = str(tmp_path / "murmur-mcp.log")
    setup(log_path=log_path)
    assert logging.getLogger().level == logging.DEBUG


def test_console_handler_level(tmp_path):
    log_path = str(tmp_path / "murmur-mcp.log")
    console, _ = setup(console_level="INFO", log_path=log_path)
    assert console.level == logging.INFO


def test_file_handler_level(tmp_path):
    log_path = str(tmp_path / "murmur-mcp.log")
    _, file = setup(file_level="WARNING", log_path=log_path)
    assert file.level == logging.WARNING


def test_log_file_created(tmp_path):
    log_path = str(tmp_path / "murmur-mcp.log")
    setup(log_path=log_path)
    assert Path(log_path).exists()


def test_log_dir_created(tmp_path):
    log_path = str(tmp_path / "subdir" / "murmur-mcp.log")
    setup(log_path=log_path)
    assert Path(log_path).parent.is_dir()
