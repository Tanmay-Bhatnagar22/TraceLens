"""Main entry point for TraceLens application."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_PATH = Path(__file__).resolve().parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.config.logging_config import get_log_file_path, get_logger, setup_logging
from gui import run_gui

def main() -> None:
    """Start TraceLens GUI with logging initialized."""
    log_file = setup_logging()
    logger = get_logger("main")
    logger.info(
        "TraceLens GUI started (Python %s on %s %s)",
        platform.python_version(),
        platform.system(),
        platform.release(),
    )
    logger.info("Application log file: %s", log_file)
    logger.info("TraceLens logging initialized. Ready for analysis.")
    try:
        run_gui()
        logger.info("TraceLens GUI closed normally.")
    except Exception as exc:
        logger.exception("TraceLens GUI terminated with an unhandled exception: %s", exc)
        raise


if __name__ == "__main__":
    main()

