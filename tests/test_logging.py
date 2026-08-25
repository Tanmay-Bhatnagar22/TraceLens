"""Unit and integration tests for TraceLens logging subsystem."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
import tempfile
import unittest.mock as mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from typer.testing import CliRunner

from src.config.logging_config import (
    add_log_listener,
    clear_logs,
    get_default_log_file,
    get_log_file_path,
    get_logger,
    get_recent_logs,
    parse_log_level,
    remove_log_listener,
    set_log_level,
    setup_logging,
)
from src.cli.cli import app


@pytest.fixture(autouse=True)
def clean_logging_state(tmp_path):
    """Ensure each test runs with a fresh logging configuration and temporary log file."""
    log_file = tmp_path / "test_tracelens.log"
    setup_logging(level="DEBUG", log_file=log_file, reset_handlers=True, log_to_console=False)
    yield
    clear_logs()


def test_parse_log_level():
    """Test log level parsing for string and numeric representations."""
    assert parse_log_level("DEBUG") == logging.DEBUG
    assert parse_log_level("info") == logging.INFO
    assert parse_log_level("WARNING") == logging.WARNING
    assert parse_log_level("ERROR") == logging.ERROR
    assert parse_log_level("CRITICAL") == logging.CRITICAL
    assert parse_log_level(logging.DEBUG) == logging.DEBUG
    assert parse_log_level("UNKNOWN_LEVEL") == logging.INFO


def test_setup_logging_creates_file(tmp_path):
    """Test setup_logging creates file handler and writes entries."""
    custom_log = tmp_path / "custom.log"
    active_file = setup_logging(level="INFO", log_file=custom_log, reset_handlers=True, log_to_console=False)

    assert active_file == custom_log.resolve()
    logger = get_logger("test.module")
    logger.info("Test info message for verification")

    # Force handler flush
    root = logging.getLogger("tracelens")
    for h in root.handlers:
        h.flush()

    assert custom_log.exists()
    content = custom_log.read_text(encoding="utf-8")
    assert "[INFO]" in content
    assert "[tracelens.test.module]" in content
    assert "Test info message for verification" in content


def test_log_level_filtering(tmp_path):
    """Test log level threshold filters out lower priority logs."""
    log_file = tmp_path / "level_test.log"
    setup_logging(level="WARNING", log_file=log_file, reset_handlers=True, log_to_console=False)
    logger = get_logger("level_checker")

    logger.debug("Debug event - should be ignored")
    logger.info("Info event - should be ignored")
    logger.warning("Warning event - should be recorded")
    logger.error("Error event - should be recorded")

    root = logging.getLogger("tracelens")
    for h in root.handlers:
        h.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "Debug event" not in content
    assert "Info event" not in content
    assert "Warning event - should be recorded" in content
    assert "Error event - should be recorded" in content


def test_memory_buffer_and_get_recent_logs():
    """Test in-memory ring buffer captures log entries."""
    logger = get_logger("memory_test")
    logger.info("Buffer message 1")
    logger.info("Buffer message 2")
    logger.info("Buffer message 3")

    recent = get_recent_logs(max_entries=2)
    assert len(recent) == 2
    assert "Buffer message 2" in recent[0]
    assert "Buffer message 3" in recent[1]


def test_clear_logs(tmp_path):
    """Test clear_logs empties both the memory buffer and the log file."""
    log_file = tmp_path / "clear_test.log"
    setup_logging(level="INFO", log_file=log_file, reset_handlers=True, log_to_console=False)
    logger = get_logger("clear_test")

    logger.info("Message before clearing")
    root = logging.getLogger("tracelens")
    for h in root.handlers:
        h.flush()

    assert len(get_recent_logs()) > 0
    assert log_file.stat().st_size > 0

    assert clear_logs() is True
    assert len(get_recent_logs()) == 0
    assert log_file.stat().st_size == 0


def test_set_log_level_dynamic(tmp_path):
    """Test dynamically modifying the log level at runtime."""
    log_file = tmp_path / "dynamic_level.log"
    setup_logging(level="WARNING", log_file=log_file, reset_handlers=True, log_to_console=False)
    logger = get_logger("dynamic_test")

    logger.info("Should not appear (initially WARNING)")
    set_log_level("DEBUG")
    logger.info("Should appear (now DEBUG)")

    root = logging.getLogger("tracelens")
    for h in root.handlers:
        h.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "Should not appear" not in content
    assert "Should appear (now DEBUG)" in content


def test_log_listeners():
    """Test registering and unregistering real-time log event callbacks."""
    captured = []

    def custom_listener(record: logging.LogRecord, formatted_msg: str):
        captured.append((record.levelname, formatted_msg))

    add_log_listener(custom_listener)
    logger = get_logger("listener_test")
    logger.info("Event for listener")

    assert len(captured) == 1
    assert captured[0][0] == "INFO"
    assert "Event for listener" in captured[0][1]

    remove_log_listener(custom_listener)
    logger.info("Event after removal")
    assert len(captured) == 1


def test_get_logger_naming():
    """Test logger hierarchy and namespace scoping."""
    l1 = get_logger("core.extractor")
    assert l1.name == "tracelens.core.extractor"

    l2 = get_logger("tracelens.gui")
    assert l2.name == "tracelens.gui"

    l3 = get_logger("tracelens")
    assert l3.name == "tracelens"


def test_env_var_configuration(monkeypatch, tmp_path):
    """Test configuring logging via environment variables."""
    env_log = tmp_path / "env_override.log"
    monkeypatch.setenv("TRACELENS_LOG_FILE", str(env_log))
    monkeypatch.setenv("TRACELENS_LOG_LEVEL", "ERROR")

    active_file = setup_logging(reset_handlers=True, log_to_console=False)
    assert active_file == env_log.resolve()

    logger = get_logger("env_test")
    logger.info("Ignored info")
    logger.error("Recorded error")

    root = logging.getLogger("tracelens")
    for h in root.handlers:
        h.flush()

    content = env_log.read_text(encoding="utf-8")
    assert "Ignored info" not in content
    assert "Recorded error" in content


def test_cli_logs_path_command():
    """Test CLI logs command with --path option."""
    runner = CliRunner()
    result = runner.invoke(app, ["logs", "--path"])
    assert result.exit_code == 0
    assert "tracelens.log" in result.stdout or "test_tracelens.log" in result.stdout


def test_cli_logs_display_command():
    """Test CLI logs command displaying recent entries."""
    logger = get_logger("cli_test")
    logger.info("Message for CLI inspect test")

    runner = CliRunner()
    result = runner.invoke(app, ["logs", "--lines", "10"])
    assert result.exit_code == 0
    assert "Message for CLI inspect test" in result.stdout


def test_cli_logs_clear_command():
    """Test CLI logs command with --clear flag."""
    logger = get_logger("cli_test")
    logger.info("Message to be cleared")

    runner = CliRunner()
    result = runner.invoke(app, ["logs", "--clear"])
    assert result.exit_code == 0
    assert "Log buffer and file cleared" in result.stdout
    assert "Message to be cleared" not in " ".join(get_recent_logs())

