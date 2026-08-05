from __future__ import annotations

from pathlib import Path
from typing import Iterable


class CLIValidationError(ValueError):
    pass


def normalize_path(raw: str) -> Path:
    cleaned = raw.strip().strip('"').strip("'")
    return Path(cleaned).expanduser()


def require_file(raw: str) -> Path:
    path = normalize_path(raw)
    if not str(path):
        raise CLIValidationError("Path cannot be empty.")
    if not path.exists():
        raise CLIValidationError(f"File not found: {path}")
    if not path.is_file():
        raise CLIValidationError(f"Path is not a file: {path}")
    return path


def require_directory(raw: str) -> Path:
    path = normalize_path(raw)
    if not str(path):
        raise CLIValidationError("Path cannot be empty.")
    if not path.exists():
        raise CLIValidationError(f"Folder not found: {path}")
    if not path.is_dir():
        raise CLIValidationError(f"Path is not a folder: {path}")
    return path


def collect_files(targets: Iterable[str], *, recursive: bool = True) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()

    for raw_target in targets:
        path = normalize_path(raw_target)
        if path.is_file():
            if path not in seen:
                files.append(path)
                seen.add(path)
            continue

        if path.is_dir():
            iterator = path.rglob("*") if recursive else path.iterdir()
            for candidate in iterator:
                if candidate.is_file() and candidate not in seen:
                    files.append(candidate)
                    seen.add(candidate)
            continue

        raise CLIValidationError(f"Path not found: {path}")

    return sorted(files)


def parse_key_value_pairs(values: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise CLIValidationError(f"Invalid key/value pair: {raw}")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise CLIValidationError(f"Invalid key/value pair: {raw}")
        result[key] = value.strip()
    return result
