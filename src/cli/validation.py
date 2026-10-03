"""Input validation and structured error types for TraceLens CLI."""

from __future__ import annotations

from enum import IntEnum
import os
from pathlib import Path
from typing import Iterable


class ExitCode(IntEnum):
    """Standardized CLI exit codes for TraceLens."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_ARGS = 2
    FILE_ERROR = 3
    DATABASE_ERROR = 4
    REPORT_ERROR = 5


class CLIError(Exception):
    """Base exception for expected CLI errors with associated exit codes."""

    default_exit_code: int = int(ExitCode.GENERAL_ERROR)

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        command: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = int(self.default_exit_code if exit_code is None else exit_code)
        self.command = command
        self.hint = hint


class CLIValidationError(CLIError, ValueError):
    """Raised when command-line arguments or inputs fail validation."""

    default_exit_code: int = int(ExitCode.INVALID_ARGS)


class CLIFileError(CLIValidationError):
    """Raised when a file or directory path does not exist, is the wrong type, or is unreadable."""

    default_exit_code: int = int(ExitCode.FILE_ERROR)


class CLIDatabaseError(CLIError):
    """Raised when a database lookup or storage operation fails."""

    default_exit_code: int = int(ExitCode.DATABASE_ERROR)


class CLIReportError(CLIError):
    """Raised when report generation or dataset export fails."""

    default_exit_code: int = int(ExitCode.REPORT_ERROR)


def normalize_path(raw: str) -> Path:
    """Strip surrounding quotes/whitespace and expand user home directory."""
    if raw is None:
        return Path("")
    cleaned = str(raw).strip().strip('"').strip("'")
    if not cleaned:
        return Path("")
    return Path(cleaned).expanduser()


def require_file(raw: str) -> Path:
    """Validate that a path exists, is a regular file (not a directory), and is readable."""
    if raw is None or not str(raw).strip().strip('"').strip("'"):
        raise CLIValidationError("Path cannot be empty.", exit_code=ExitCode.INVALID_ARGS)

    path = normalize_path(raw)
    if not path.exists():
        raise CLIFileError(f"File not found: {path}")
    if path.is_dir():
        raise CLIFileError(f"Path is a directory, expected a file: {path}")
    if not path.is_file():
        raise CLIFileError(f"Path is not a file: {path}")
    if not os.access(path, os.R_OK):
        raise CLIFileError(f"File is not readable (permission denied): {path}")

    try:
        with path.open("rb"):
            pass
    except PermissionError as exc:
        raise CLIFileError(f"File is not readable (permission denied): {path}") from exc
    except OSError as exc:
        raise CLIFileError(f"Cannot read file '{path}': {exc}") from exc

    return path


def require_directory(raw: str) -> Path:
    """Validate that a path exists, is a directory, and can be accessed."""
    if raw is None or not str(raw).strip().strip('"').strip("'"):
        raise CLIValidationError("Path cannot be empty.", exit_code=ExitCode.INVALID_ARGS)

    path = normalize_path(raw)
    if not path.exists():
        raise CLIFileError(f"Folder not found: {path}")
    if path.is_file():
        raise CLIFileError(f"Path is a file, expected a directory: {path}")
    if not path.is_dir():
        raise CLIFileError(f"Path is not a folder: {path}")
    if not os.access(path, os.R_OK):
        raise CLIFileError(f"Directory is not accessible (permission denied): {path}")

    try:
        next(path.iterdir(), None)
    except PermissionError as exc:
        raise CLIFileError(f"Directory is not accessible (permission denied): {path}") from exc
    except OSError as exc:
        raise CLIFileError(f"Cannot access directory '{path}': {exc}") from exc

    return path


def validate_record_id(raw: str | int) -> int:
    """Validate that a record identifier is a positive integer."""
    if isinstance(raw, bool):
        raise CLIValidationError(f"Invalid record ID '{raw}': must be an integer.", exit_code=ExitCode.INVALID_ARGS)
    text = str(raw).strip()
    if not text:
        raise CLIValidationError("Record ID cannot be empty.", exit_code=ExitCode.INVALID_ARGS)
    try:
        record_id = int(text)
    except ValueError as exc:
        raise CLIValidationError(
            f"Invalid record ID '{raw}': must be an integer.",
            exit_code=ExitCode.INVALID_ARGS,
        ) from exc
    if record_id <= 0:
        raise CLIValidationError(
            f"Invalid record ID '{raw}': must be a positive integer.",
            exit_code=ExitCode.INVALID_ARGS,
        )
    return record_id


def validate_search_query(raw: str) -> str:
    """Validate that a search query string is not empty or whitespace-only."""
    if raw is None:
        raise CLIValidationError("Search query cannot be empty.", exit_code=ExitCode.INVALID_ARGS)
    cleaned = str(raw).strip()
    if not cleaned:
        raise CLIValidationError("Search query cannot be empty.", exit_code=ExitCode.INVALID_ARGS)
    return cleaned


def collect_files(
    targets: Iterable[str],
    *,
    recursive: bool = True,
    allow_directories: bool = True,
) -> list[Path]:
    """Collect and validate file paths from one or more file/directory targets."""
    files: list[Path] = []
    seen: set[Path] = set()

    for raw_target in targets:
        if not allow_directories:
            file_path = require_file(raw_target)
            if file_path not in seen:
                files.append(file_path)
                seen.add(file_path)
            continue

        if raw_target is None or not str(raw_target).strip().strip('"').strip("'"):
            raise CLIValidationError("Path cannot be empty.", exit_code=ExitCode.INVALID_ARGS)

        path = normalize_path(raw_target)
        if not path.exists():
            raise CLIFileError(f"File not found: {path}")

        if path.is_file():
            checked = require_file(raw_target)
            if checked not in seen:
                files.append(checked)
                seen.add(checked)
            continue

        if path.is_dir():
            checked_dir = require_directory(raw_target)
            iterator = checked_dir.rglob("*") if recursive else checked_dir.iterdir()
            for candidate in iterator:
                try:
                    if candidate.is_file() and candidate not in seen:
                        files.append(candidate)
                        seen.add(candidate)
                except OSError:
                    continue
            continue

        raise CLIFileError(f"Path not found: {path}")

    return sorted(files)


def parse_key_value_pairs(values: Iterable[str]) -> dict[str, str]:
    """Parse KEY=VALUE strings into a dictionary."""
    result: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise CLIValidationError(f"Invalid key/value pair '{raw}' (expected KEY=VALUE).")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise CLIValidationError(f"Invalid key/value pair '{raw}' (key cannot be empty).")
        result[key] = value.strip()
    return result
