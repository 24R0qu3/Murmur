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


@pytest.mark.parametrize(
    "flag,expected",
    [
        ([], "WARNING"),
        (["--log", "DEBUG"], "DEBUG"),
        (["--log", "INFO"], "INFO"),
    ],
)
def test_log_flag(flag, expected):
    import argparse

    from murmur.main import LEVELS

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--log", default="WARNING", choices=LEVELS)
    parser.add_argument("--log-file", default="DEBUG", choices=LEVELS)
    parser.add_argument("--log-path", default=None)
    args, _ = parser.parse_known_args(flag)
    assert args.log == expected


def test_custom_log_path(tmp_path):
    import argparse

    from murmur.main import LEVELS

    log_path = str(tmp_path / "custom.log")
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--log", default="WARNING", choices=LEVELS)
    parser.add_argument("--log-file", default="DEBUG", choices=LEVELS)
    parser.add_argument("--log-path", default=None)
    args, _ = parser.parse_known_args(["--log-path", log_path])
    assert args.log_path == log_path
