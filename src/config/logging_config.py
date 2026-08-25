"""Centralized logging configuration and utilities for TraceLens.

Provides robust logging setup for both CLI and GUI modes, including:
- Rotating file handler with user-writable default paths.
- Configurable console stream handler.
- In-memory ring buffer for live log inspection in GUI and CLI.
- Scoped logger retrieval with hierarchy `tracelens.<module>`.
- Environment variable overrides:
  - TRACELENS_LOG_LEVEL (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - TRACELENS_LOG_FILE (explicit log file destination)
  - TRACELENS_LOG_DIR (directory to hold tracelens.log)
"""

from __future__ import annotations

import collections
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable

# Default format strings
LOG_FORMAT_DETAILED = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
LOG_FORMAT_SIMPLE = "[%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Global state
_IS_INITIALIZED = False
_CURRENT_LOG_FILE: Path | None = None
_MEMORY_BUFFER_SIZE = 1000
_MEMORY_BUFFER: collections.deque[str] = collections.deque(maxlen=_MEMORY_BUFFER_SIZE)
_MEMORY_HANDLER: MemoryBufferHandler | None = None
_LOG_LISTENERS: list[Callable[[logging.LogRecord, str], None]] = []


class MemoryBufferHandler(logging.Handler):
    """Logging handler that stores recent formatted log entries in memory."""

    def __init__(self, buffer: collections.deque[str]) -> None:
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.buffer.append(msg)
            for listener in list(_LOG_LISTENERS):
                try:
                    listener(record, msg)
                except Exception:
                    pass
        except Exception:
            self.handleError(record)


def _default_log_dir() -> Path:
    """Determine a safe, user-writable directory for TraceLens logs."""
    env_dir = os.getenv("TRACELENS_LOG_DIR")
    if env_dir:
        dir_path = Path(env_dir)
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        except Exception:
            pass

    if os.name == "nt":
        base_dir = os.getenv("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base_dir = os.getenv("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")

    log_dir = Path(base_dir) / "TraceLens" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    except Exception:
        fallback = Path(tempfile.gettempdir()) / "TraceLens" / "logs"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback
        except Exception:
            return Path(tempfile.gettempdir())


def get_default_log_file() -> Path:
    """Get the default path for the main application log file."""
    env_file = os.getenv("TRACELENS_LOG_FILE")
    if env_file:
        return Path(env_file).resolve()
    return _default_log_dir() / "tracelens.log"


def parse_log_level(level: str | int | None) -> int:
    """Convert string or integer log level to standard logging constant."""
    if level is None:
        env_level = os.getenv("TRACELENS_LOG_LEVEL", "INFO").upper().strip()
        return getattr(logging, env_level, logging.INFO)

    if isinstance(level, int):
        return level

    level_upper = str(level).strip().upper()
    return getattr(logging, level_upper, logging.INFO)


def setup_logging(
    level: str | int | None = None,
    log_file: str | Path | None = None,
    log_to_file: bool = True,
    log_to_console: bool = True,
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 3,
    reset_handlers: bool = False,
) -> Path | None:
    """Initialize application logging configuration for TraceLens.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) or logging constant.
        log_file: Custom file path for log destination.
        log_to_file: Whether to attach a rotating file handler.
        log_to_console: Whether to attach a console stream handler.
        max_bytes: Maximum size per log file before rotation.
        backup_count: Number of rotated backup log files to retain.
        reset_handlers: If True, remove existing handlers before attaching new ones.

    Returns:
        Path to the active log file if file logging is enabled, else None.
    """
    global _IS_INITIALIZED, _CURRENT_LOG_FILE, _MEMORY_HANDLER

    log_level = parse_log_level(level)
    root_logger = logging.getLogger("tracelens")
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if already initialized and reset not requested
    if _IS_INITIALIZED and not reset_handlers:
        root_logger.setLevel(log_level)
        return _CURRENT_LOG_FILE

    if reset_handlers or not _IS_INITIALIZED:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

        formatter = logging.Formatter(fmt=LOG_FORMAT_DETAILED, datefmt=LOG_DATE_FORMAT)

        # 1. In-memory buffer handler (always attached for UI / CLI introspection)
        _MEMORY_HANDLER = MemoryBufferHandler(_MEMORY_BUFFER)
        _MEMORY_HANDLER.setFormatter(formatter)
        _MEMORY_HANDLER.setLevel(logging.DEBUG)  # capture all records into buffer
        root_logger.addHandler(_MEMORY_HANDLER)

        # 2. Rotating File Handler
        target_log_file: Path | None = None
        if log_to_file:
            if log_file is not None:
                target_log_file = Path(log_file).resolve()
            else:
                target_log_file = get_default_log_file()

            try:
                target_log_file.parent.mkdir(parents=True, exist_ok=True)
                file_handler = RotatingFileHandler(
                    filename=str(target_log_file),
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                    delay=True,
                )
                file_handler.setFormatter(formatter)
                file_handler.setLevel(log_level)
                root_logger.addHandler(file_handler)
                _CURRENT_LOG_FILE = target_log_file
            except Exception as exc:
                sys.stderr.write(f"[TraceLens Logging Warning] Could not open log file {target_log_file}: {exc}\n")
                target_log_file = None

        # 3. Console Stream Handler
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(log_level)
            root_logger.addHandler(console_handler)

        _IS_INITIALIZED = True
        return target_log_file

    return _CURRENT_LOG_FILE


def get_logger(name: str = "tracelens") -> logging.Logger:
    """Retrieve a logger scoped under the `tracelens` hierarchy.

    Args:
        name: Name of the logger or module.

    Returns:
        Configured Logger instance.
    """
    if not _IS_INITIALIZED:
        setup_logging()

    if name.startswith("tracelens.") or name == "tracelens":
        return logging.getLogger(name)
    return logging.getLogger(f"tracelens.{name}")


def get_log_file_path() -> Path | None:
    """Return the path to the currently active log file."""
    return _CURRENT_LOG_FILE or get_default_log_file()


def get_recent_logs(max_entries: int = 100) -> list[str]:
    """Retrieve recent log entries from the in-memory ring buffer or active log file.

    Args:
        max_entries: Maximum number of recent log lines to retrieve.

    Returns:
        List of log line strings.
    """
    if _MEMORY_BUFFER:
        return list(_MEMORY_BUFFER)[-max_entries:]

    log_path = get_log_file_path()
    if log_path and log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                return [line.rstrip("\r\n") for line in lines[-max_entries:]]
        except Exception:
            return []
    return []


def clear_logs() -> bool:
    """Clear memory buffer and truncate the active log file if present.

    Returns:
        True if successfully cleared, False otherwise.
    """
    _MEMORY_BUFFER.clear()
    log_path = get_log_file_path()
    if log_path and log_path.exists():
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("")
            return True
        except Exception:
            return False
    return True


def set_log_level(level: str | int) -> None:
    """Dynamically change the log level for all TraceLens handlers.

    Args:
        level: New log level (e.g. 'DEBUG', 'INFO', 'WARNING', logging.DEBUG, etc.).
    """
    new_level = parse_log_level(level)
    root_logger = logging.getLogger("tracelens")
    root_logger.setLevel(new_level)
    for handler in root_logger.handlers:
        if not isinstance(handler, MemoryBufferHandler):
            handler.setLevel(new_level)


def add_log_listener(callback: Callable[[logging.LogRecord, str], None]) -> None:
    """Register a callback for real-time log event streaming (e.g. GUI log viewer)."""
    if callback not in _LOG_LISTENERS:
        _LOG_LISTENERS.append(callback)


def remove_log_listener(callback: Callable[[logging.LogRecord, str], None]) -> None:
    """Unregister a previously registered log listener callback."""
    if callback in _LOG_LISTENERS:
        _LOG_LISTENERS.remove(callback)
