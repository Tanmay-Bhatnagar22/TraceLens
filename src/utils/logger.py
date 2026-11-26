"""Logger utility helpers and aliases for TraceLens."""

from __future__ import annotations

import logging
from src.config.logging_config import (
    add_log_listener,
    clear_logs,
    get_default_log_file,
    get_log_file_path,
    get_logger,
    get_recent_logs,
    remove_log_listener,
    set_log_level,
    setup_logging,
)

__all__ = [
    "add_log_listener",
    "clear_logs",
    "get_default_log_file",
    "get_log_file_path",
    "get_logger",
    "get_recent_logs",
    "remove_log_listener",
    "set_log_level",
    "setup_logging",
]
