"""TraceLens command-line interface.

This module exposes the production CLI entrypoint powered by standard library
``argparse`` (`build_parser`, `main`) with centralized error handling, input
validation, consistent formatting, exit codes, a single canonical help system
(`render_full_help`), and full support for the TraceLens service layer
(`ServiceContainer`, `ExtractionService`, `RiskAnalysisService`,
`MetadataEditorService`, `HistoryService`, `ReportService`, `AnalyticsService`).

Note: The Tkinter GUI is packaged as a separate executable starting in TraceLens v2
and is intentionally decoupled from the CLI startup and execution path.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
import traceback
from typing import Any

import pandas as pd
from rich import box
from rich.panel import Panel
from rich.table import Table
import typer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT_DIR = PROJECT_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import __version__
from src.cli.output import (
    console,
    mapping_table,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    records_table,
    risk_table,
    summary_panel,
    timeline_table,
)
from src.cli.validation import (
    CLIDatabaseError,
    CLIError,
    CLIFileError,
    CLIReportError,
    CLIValidationError,
    ExitCode,
    collect_files,
    normalize_path,
    parse_key_value_pairs,
    require_directory,
    require_file,
    validate_record_id,
    validate_search_query,
)
from src.config.logging_config import (
    add_log_listener,
    clear_logs,
    get_log_file_path,
    get_logger,
    get_recent_logs,
    remove_log_listener,
    set_log_level,
    setup_logging,
)

# Initialize CLI logging without console stream noise before importing core engines
setup_logging(log_to_console=False)

from src.core.database import db as db_core
from src.core.editor import editor as editor_core
from src.core.extractor import extractor as extractor_core
from src.core.reports import report as report_core
from src.core.risk import risk_analyzer as risk_core
from src.core.services import (
    ServiceContainer,
    get_service_container,
    set_service_container,
)
from src.models import RiskAssessment

logger = get_logger("cli")

# Backward-compatibility module references for service injection and tests
db = db_core
editor = editor_core
extractor = extractor_core
report = report_core
risk_analyzer = risk_core

APP_VERSION = __version__

# Standardized CLI exit codes
EXIT_SUCCESS = int(ExitCode.SUCCESS)
EXIT_GENERAL_ERROR = int(ExitCode.GENERAL_ERROR)
EXIT_INVALID_ARGS = int(ExitCode.INVALID_ARGS)
EXIT_FILE_ERROR = int(ExitCode.FILE_ERROR)
EXIT_DATABASE_ERROR = int(ExitCode.DATABASE_ERROR)
EXIT_REPORT_ERROR = int(ExitCode.REPORT_ERROR)

DB_COLUMNS = [
    "id",
    "file_path",
    "file_name",
    "file_size_formatted",
    "file_type",
    "extracted_at",
    "modified_on",
    "full_metadata",
]


@dataclass
class CLIState:
    """Runtime configuration and dependency container for the CLI session."""

    verbose: bool = False
    quiet: bool = False
    db_path: str | None = None
    container: ServiceContainer | None = None


_active_state: CLIState = CLIState()


def _get_state() -> CLIState:
    return _active_state


def get_services(state: CLIState | None = None) -> ServiceContainer:
    """Retrieve the active ServiceContainer, either from state, singleton, or dynamically configured."""
    if state is not None and state.container is not None:
        return state.container

    current_state = state or _get_state()
    if current_state.container is not None:
        return current_state.container

    custom_db = db if db is not db_core else None
    custom_extractor = extractor if extractor is not extractor_core else None
    custom_analyzer = risk_analyzer if risk_analyzer is not risk_core else None
    custom_editor = editor if editor is not editor_core else None
    custom_reporter = report if report is not report_core else None

    if (
        current_state.db_path
        or custom_db
        or custom_extractor
        or custom_analyzer
        or custom_editor
        or custom_reporter
    ):
        container = ServiceContainer(
            db_path=current_state.db_path,
            database=custom_db,
            extractor=custom_extractor,
            analyzer=custom_analyzer,
            editor=custom_editor,
            reporter=custom_reporter,
        )
    else:
        container = get_service_container(db_path=current_state.db_path)

    current_state.container = container
    return container


def set_services(container: ServiceContainer | None) -> None:
    """Set the active ServiceContainer for the CLI and global context."""
    global _active_state
    set_service_container(container)
    _active_state.container = container


def _configure_session_state(
    *,
    verbose: bool = False,
    quiet: bool = False,
    db_path: str | None = None,
) -> CLIState:
    """Initialize CLIState and logging configuration for a CLI invocation."""
    global _active_state
    existing = _active_state.container
    if existing is not None and (
        not db_path or str(getattr(existing.database, "db_path", "")) == str(db_path)
    ):
        container = existing
    elif db_path:
        container = ServiceContainer(db_path=db_path)
    else:
        container = None

    state = CLIState(
        verbose=verbose,
        quiet=quiet,
        db_path=db_path,
        container=container,
    )
    _active_state = state

    level = "DEBUG" if verbose else ("WARNING" if quiet else "INFO")
    setup_logging(level=level, log_to_console=False)
    set_log_level(level)
    root_logger = logging.getLogger("tracelens")
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(logging.CRITICAL + 1)

    return state


def _emit_header(state: CLIState | None = None) -> None:
    active = state or _get_state()
    if not active.quiet:
        print_header("TraceLens")


def _normalize_path(raw: str) -> str:
    return str(normalize_path(raw))


def _row_to_record(row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(DB_COLUMNS, row, strict=False))


def _load_record(record_id: int) -> dict[str, Any] | None:
    services = get_services()
    record = services.history.get_record_by_id(record_id)
    if not record:
        return None
    return record.to_dict()


def _summarize_history_rows(rows: list[dict[str, Any]], *, title: str = "History") -> None:
    if not rows:
        print_warning("No history records found.")
        return

    console.print(records_table(rows, title=title))
    console.print(summary_panel("Summary", [f"Records shown: {len(rows)}"], style="cyan"))


def _history_rows(
    *,
    limit: int,
    query: str,
    file_type: str,
    date_filter: str,
    sort: str,
) -> list[tuple[Any, ...]]:
    services = get_services()
    has_filters = any([query.strip(), file_type != "All", date_filter != "All Time", sort != "Date (Newest)"])
    if has_filters:
        rows = services.database.filter_and_search_data(query, file_type, date_filter, sort)
        if limit > 0:
            return rows[:limit]
        return rows
    if limit > 0:
        return services.database.get_recent_records(limit=limit)
    return services.database.fetch_all_metadata()


def _preview_report_text(text: str, *, limit: int = 1400) -> str:
    return text[:limit] + ("\n..." if len(text) > limit else "")


def _default_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _choose_source_metadata(source: str) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    """Resolve report source from either a valid integer record ID or an existing file path."""
    services = get_services()
    if not source or not str(source).strip():
        raise CLIValidationError("Report source cannot be empty.", command="report", exit_code=ExitCode.INVALID_ARGS)

    cleaned = str(source).strip()

    source_path = normalize_path(cleaned)
    if source_path.exists():
        if source_path.is_dir():
            raise CLIFileError(
                f"Path is a directory, expected a file or record ID: {source_path}",
                command="report",
            )
        checked_file = require_file(cleaned)
        res = services.extraction.extract_file(str(checked_file), persist=False)
        if not res.success or not isinstance(res.metadata, dict) or "Error" in res.metadata:
            raise CLIFileError(res.error or f"Failed to extract metadata from {checked_file}", command="report")
        return str(checked_file), res.metadata, None

    if any(sep in cleaned for sep in ("/", "\\")) or (
        "." in Path(cleaned).name and not cleaned.lstrip("-").isdigit()
    ):
        raise CLIFileError(f"File not found: {source_path}", command="report")

    record_id = validate_record_id(cleaned)
    try:
        record = _load_record(record_id)
    except Exception as exc:
        raise CLIDatabaseError(f"Database error while fetching record {record_id}: {exc}", command="report") from exc

    if not record:
        raise CLIDatabaseError(f"No history record found for ID {record_id}.", command="report")

    return record["file_path"], record["full_metadata"], record


# ==============================================================================
# Command Handlers
# ==============================================================================


def _handle_extract(
    targets: list[str],
    *,
    no_save: bool = False,
    recursive: bool = False,
    details: bool = False,
    state: CLIState,
) -> int:
    services = get_services(state)
    logger.debug("Extract command invoked for targets=%s (save_to_db=%s, recursive=%s)", targets, not no_save, recursive)

    if recursive:
        validated_files = collect_files(targets, recursive=True, allow_directories=True)
        for file_path in validated_files:
            logger.info("Validating file: %s", file_path.name)
    else:
        validated_files = []
        for raw_target in targets:
            file_path = require_file(raw_target)
            logger.info("Validating file: %s", file_path.name)
            try:
                size_bytes = file_path.stat().st_size
                logger.info("File size: %d bytes", size_bytes)
            except OSError as exc:
                raise CLIFileError(f"Cannot stat file '{file_path}': {exc}", command="extract") from exc
            validated_files.append(file_path)

    if len(validated_files) == 1:
        file_path = validated_files[0]
        logger.info("Extracting metadata")
        if not no_save:
            logger.info("Storing metadata in database")

        result = services.extraction.extract_file(str(file_path), persist=not no_save)
        if not result.success:
            err_msg = result.error or "Extraction failed."
            if "persist" in err_msg.lower() or "database" in err_msg.lower():
                raise CLIDatabaseError(err_msg, command="extract")
            raise CLIFileError(err_msg, command="extract")

        fmt = str(
            result.metadata.get("Format")
            or result.metadata.get("File Type")
            or result.file_type
            or file_path.suffix.lstrip(".")
            or "UNKNOWN"
        ).upper()
        field_count = len(result.metadata) if isinstance(result.metadata, dict) else 0

        _emit_header(state)
        print_success("Metadata extraction completed")
        print()

        summary_lines = [
            f"Metadata for {file_path.name}",
            f"File: {file_path.name}",
            f"Path: {file_path}",
            f"Format: {fmt}",
            f"Metadata fields: {field_count}",
            f"Saved to database: {'no' if no_save else 'yes'}",
        ]
        if result.db_record_id:
            summary_lines.append(f"Record ID: {result.db_record_id}")

        for line in summary_lines[1:]:
            print(line)
        print()

        if state.verbose or details:
            console.print(mapping_table(f"Metadata for {file_path.name}", result.metadata))

        console.print(summary_panel("Extraction Complete", summary_lines, style="green"))
        return EXIT_SUCCESS

    return _run_batch_files(validated_files, no_save=no_save, state=state, command_name="extract")


def _run_batch_files(
    files: list[Path],
    *,
    no_save: bool,
    state: CLIState,
    command_name: str = "batch",
) -> int:
    services = get_services(state)
    total = len(files)
    _emit_header(state)

    if total == 0:
        print_warning("No files were found to process.")
        summary_lines = [
            "Files discovered: 0",
            "Processed: 0",
            "Total: 0",
            "Successful: 0",
            "Failed: 0",
        ]
        for line in summary_lines:
            print(line)
        console.print(summary_panel("Batch processing complete", summary_lines, style="yellow"))
        return EXIT_SUCCESS

    entries: list[dict[str, Any]] = []
    failures: list[tuple[str, str]] = []

    for idx, file_path in enumerate(files, start=1):
        print(f"Processing {idx}/{total}: {file_path.name}")
        logger.info("Processing %d/%d: %s", idx, total, file_path)
        try:
            result = services.extraction.extract_file(str(file_path), persist=not no_save)
            if not result.success:
                reason = result.error or "Extraction failed."
                failures.append((file_path.name, reason))
                logger.warning("Failed extraction on batch file %s: %s", file_path, reason)
            else:
                entries.append({"file_path": str(file_path), "metadata": result.metadata})
        except Exception as exc:
            reason = str(exc) or "Unexpected extraction error"
            failures.append((file_path.name, reason))
            logger.warning("Exception while processing batch file %s: %s", file_path, exc)

    successful = len(entries)
    failed = len(failures)

    batch_risk = services.risk.analyze_batch(entries) if entries else None
    low_cnt = batch_risk.low_risk_count if batch_risk else 0
    med_cnt = batch_risk.medium_risk_count if batch_risk else 0
    high_cnt = batch_risk.high_risk_count if batch_risk else 0

    print()
    print_success("Batch processing complete")
    print()

    summary_lines = [
        f"Files discovered: {total}",
        f"Processed: {successful}",
        f"Total: {total}",
        f"Successful: {successful}",
        f"Failed: {failed}",
        f"LOW: {low_cnt}",
        f"MEDIUM: {med_cnt}",
        f"HIGH: {high_cnt}",
    ]
    for line in summary_lines:
        print(line)

    if failures:
        print("\nFailed files:")
        for fname, err in failures:
            print(f"  - {fname}: {err}")

    console.print(
        summary_panel(
            "Batch Extraction Summary",
            summary_lines,
            style="green" if failed == 0 else "yellow",
        )
    )
    if state.verbose and batch_risk and batch_risk.assessments:
        highest = max(batch_risk.assessments, key=lambda a: a.risk_score, default=None)
        if highest:
            console.print(
                summary_panel(
                    "Highest Risk Item",
                    [json.dumps(highest.to_dict(), indent=2, default=str)],
                    style="yellow",
                )
            )

    if successful == 0 and failed > 0:
        return EXIT_GENERAL_ERROR
    return EXIT_SUCCESS


def _handle_batch(
    directory: str,
    *,
    recursive: bool = True,
    no_save: bool = False,
    state: CLIState,
) -> int:
    logger.info("Validating directory: %s", directory)
    folder = require_directory(directory)

    iterator = folder.rglob("*") if recursive else folder.iterdir()
    files: list[Path] = []
    for candidate in iterator:
        try:
            if candidate.is_file():
                files.append(candidate)
        except OSError:
            continue
    files.sort()

    logger.info("Discovered %d file(s) in %s", len(files), folder)
    return _run_batch_files(files, no_save=no_save, state=state, command_name="batch")


def _handle_analyze(
    targets: list[str],
    *,
    recursive: bool = True,
    threshold: int = 0,
    no_save: bool = True,
    state: CLIState,
) -> int:
    services = get_services(state)
    logger.info("Analyze command invoked for targets: %s (recursive=%s)", targets, recursive)

    files = collect_files(targets, recursive=recursive, allow_directories=True)
    if not files:
        _emit_header(state)
        print_warning("No files were found in the provided target(s).")
        return EXIT_SUCCESS

    analyses: list[RiskAssessment] = []
    failed_items: list[tuple[str, str]] = []
    total = len(files)

    for idx, file_path in enumerate(files, start=1):
        logger.info("Validating file: %s", file_path.name)
        if total > 1:
            print(f"Processing {idx}/{total}: {file_path.name}")
        logger.info("Extracting metadata for risk analysis: %s", file_path.name)
        ext_res = services.extraction.extract_file(str(file_path), persist=not no_save)
        if not ext_res.success:
            failed_items.append((file_path.name, ext_res.error or "Extraction failed."))
        else:
            logger.info("Evaluating privacy and forensic risk rules")
            assessment = services.risk.analyze_metadata(ext_res.metadata, str(file_path))
            if assessment.risk_score >= threshold:
                analyses.append(assessment)

    _emit_header(state)

    if total == 1:
        if failed_items:
            raise CLIFileError(failed_items[0][1], command="analyze")
        if not analyses:
            print_info(f"File risk score is below threshold ({threshold}).")
            return EXIT_SUCCESS

        analysis = analyses[0]
        print_success("Risk analysis completed")
        print()
        console.print(risk_table(analysis.to_dict()))
        reasons = analysis.reasons or []
        if reasons:
            console.print(summary_panel("Reasons", [f"- {reason}" for reason in reasons], style="yellow"))
        timeline = analysis.timeline or []
        if timeline:
            console.print(timeline_table(timeline))
        suggestions = services.risk.get_remediation_suggestions(analysis)
        if suggestions:
            console.print(summary_panel("Remediation Suggestions", [f"- {s}" for s in suggestions], style="cyan"))
        console.print(
            summary_panel(
                "Analysis Complete",
                [
                    f"File: {analysis.file_name or files[0].name}",
                    f"Risk Score: {analysis.risk_score}/100",
                    f"Risk Level: {analysis.risk_level}",
                ],
                style="green",
            )
        )
        return EXIT_SUCCESS

    summary_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "ERROR": len(failed_items)}
    for item in analyses:
        summary_counts[item.risk_level] = summary_counts.get(item.risk_level, 0) + 1

    print_success("Batch risk analysis completed")
    console.print(
        summary_panel(
            "Batch Analysis Summary",
            [
                f"Files analyzed: {len(analyses)}",
                f"LOW: {summary_counts.get('LOW', 0)}",
                f"MEDIUM: {summary_counts.get('MEDIUM', 0)}",
                f"HIGH: {summary_counts.get('HIGH', 0)}",
                f"Errors: {summary_counts.get('ERROR', 0)}",
            ],
            style="green" if not failed_items else "yellow",
        )
    )
    if state.verbose and analyses:
        console.print(
            records_table(
                [
                    {
                        "id": index + 1,
                        "file_name": item.file_name,
                        "file_type": item.risk_level,
                        "file_size_formatted": str(item.risk_score),
                        "extracted_at": "",
                        "file_path": item.file_path,
                    }
                    for index, item in enumerate(analyses)
                ],
                title="Analysis Results",
            )
        )
    return EXIT_SUCCESS if analyses or not failed_items else EXIT_GENERAL_ERROR


def _handle_search(
    query: str,
    *,
    file_type: str = "All",
    date_filter: str = "All Time",
    sort: str = "Date (Newest)",
    limit: int = 20,
    state: CLIState,
) -> int:
    cleaned_query = validate_search_query(query)
    if limit <= 0:
        raise CLIValidationError("Limit must be a positive integer.", command="search")

    logger.info("Searching database records for query='%s' (type=%s, limit=%d)", cleaned_query, file_type, limit)
    try:
        rows = _history_rows(
            limit=limit,
            query=cleaned_query,
            file_type=file_type,
            date_filter=date_filter,
            sort=sort,
        )
    except Exception as exc:
        raise CLIDatabaseError(f"Database search failed: {exc}", command="search") from exc

    _emit_header(state)
    if not rows:
        print_warning(f"No matching records found for query: '{cleaned_query}'")
        return EXIT_SUCCESS

    display_rows = [_row_to_record(row) for row in rows]
    print_success("Search completed")
    print(f"Query: {cleaned_query}")
    print(f"Matches: {len(display_rows)}")
    for row in display_rows:
        print(f"  [{row.get('id')}] {row.get('file_name')} ({row.get('file_type')})")
    _summarize_history_rows(display_rows, title=f"Search Results: '{cleaned_query}'")
    return EXIT_SUCCESS


def _handle_sanitize(
    targets: list[str],
    *,
    backup: bool = True,
    recursive: bool = True,
    dry_run: bool = False,
    state: CLIState,
) -> int:
    services = get_services(state)
    logger.info("Sanitize command invoked for targets: %s (backup=%s, recursive=%s)", targets, backup, recursive)
    files = collect_files(targets, recursive=recursive, allow_directories=True)
    if not files:
        raise CLIFileError("No files were found in the provided target(s).", command="sanitize")

    sanitized = 0
    failed = 0
    results: list[str] = []
    total = len(files)

    for idx, file_path in enumerate(files, start=1):
        if total > 1:
            print(f"Processing {idx}/{total}: {file_path.name}")
        if dry_run:
            sanitized += 1
            results.append(f"Dry-run: {file_path.name}")
            continue
        success, msg = services.sanitize_file(str(file_path), backup=backup)
        if success:
            sanitized += 1
            results.append(f"Sanitized: {file_path.name}")
        else:
            failed += 1
            results.append(f"Failed: {file_path.name} - {msg}")

    _emit_header(state)
    if sanitized > 0:
        print_success("Metadata sanitization completed")
    console.print(
        summary_panel(
            "Sanitization Summary",
            [
                f"Total targets: {len(files)}",
                f"Successfully sanitized: {sanitized}",
                f"Failed/Unsupported: {failed}",
                f"Backup enabled: {'yes' if backup else 'no'}",
            ]
            + (results[:10] if not state.quiet else []),
            style="green" if failed == 0 else "yellow",
        )
    )
    if sanitized == 0 and failed > 0:
        raise CLIError("Failed to sanitize target file(s).", command="sanitize", exit_code=ExitCode.GENERAL_ERROR)
    return EXIT_SUCCESS


def _handle_edit(
    file_path: str,
    *,
    set_values: list[str] | None = None,
    metadata_file: str | None = None,
    write_file: bool = True,
    save_db: bool = True,
    state: CLIState,
) -> int:
    services = get_services(state)
    source = require_file(file_path)

    updates: dict[str, Any] = {}
    if set_values:
        updates.update(parse_key_value_pairs(set_values))

    if metadata_file:
        payload_path = require_file(metadata_file)
        try:
            loaded = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CLIValidationError(f"Invalid metadata JSON file '{metadata_file}': {exc}", command="edit") from exc
        if not isinstance(loaded, dict):
            raise CLIValidationError("Metadata file must contain a JSON object.", command="edit")
        updates.update(loaded)

    if not updates:
        raise CLIValidationError("No metadata changes were supplied. Use --set KEY=VALUE or --metadata-file.", command="edit")

    ext_res = services.extraction.extract_file(str(source), persist=False)
    if ext_res.success and ext_res.metadata:
        base_metadata = ext_res.metadata
    else:
        latest_record = services.history.get_latest_by_path(str(source))
        if latest_record and latest_record.full_metadata:
            base_metadata = latest_record.full_metadata
        else:
            raise CLIFileError(ext_res.error or "Extraction failed.", command="edit")

    editable_text = services.editor.get_editable_text((str(source), base_metadata))
    parsed = services.editor.parse_editor_text(editable_text)
    parsed["metadata"].update(updates)

    is_valid, val_msg = services.editor.validate_metadata(parsed)
    if not is_valid:
        raise CLIValidationError(f"Metadata validation error: {val_msg}", command="edit")

    db_result = (False, "Database update disabled")
    file_result = (False, "File write disabled")

    logger.info("Editing metadata for source: %s (updates=%s, save_db=%s, write_file=%s)", source, updates, save_db, write_file)
    if save_db:
        db_result = services.editor.save_to_database(str(source), parsed)
    if write_file:
        file_result = services.editor.write_to_file(str(source), parsed, backup=True)

    _emit_header(state)
    print_success("Metadata update completed")
    changed_fields = [f"{key}: {value}" for key, value in updates.items()]
    console.print(summary_panel("Metadata Edit", changed_fields, style="green"))
    console.print(
        summary_panel(
            "Persistence",
            [
                f"Database: {'success' if db_result[0] else 'skipped/failed'} - {db_result[1]}",
                f"File write: {'success' if file_result[0] else 'skipped/failed'} - {file_result[1]}",
            ],
            style="cyan",
        )
    )
    if not db_result[0] and not file_result[0]:
        raise CLIError("Failed to persist metadata changes to database or file.", command="edit")
    return EXIT_SUCCESS


def _handle_report(
    source: str,
    *,
    format_name: str = "both",
    output_dir: str = str(PROJECT_ROOT),
    state: CLIState,
) -> int:
    services = get_services(state)
    fmt = (format_name or "both").strip().lower()
    if fmt not in {"txt", "pdf", "both"}:
        raise CLIValidationError(
            f"Invalid report format '{format_name}'. Supported formats: txt, pdf, both.",
            command="report",
        )

    logger.info("Report command invoked for source: %s (format=%s, output_dir=%s)", source, fmt, output_dir)
    file_path_text, metadata, record = _choose_source_metadata(source)

    try:
        output_directory = Path(output_dir).expanduser()
        output_directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CLIReportError(f"Cannot create report output directory '{output_dir}': {exc}", command="report") from exc

    try:
        analysis = services.risk.analyze_metadata(metadata, file_path_text)
        text_report = services.report.generate_text_report(metadata, file_path_text, risk_analysis=analysis.to_dict())
    except Exception as exc:
        raise CLIReportError(f"Failed to build report content: {exc}", command="report") from exc

    base_name = Path(file_path_text).stem or "tracelens_report"
    timestamp = _default_timestamp()
    outputs: list[Path] = []

    if fmt in {"txt", "both"}:
        txt_path = output_directory / f"{base_name}_report_{timestamp}.txt"
        try:
            txt_path.write_text(text_report, encoding="utf-8")
            outputs.append(txt_path)
            logger.info("Generated text report: %s", txt_path)
        except OSError as exc:
            raise CLIReportError(f"Failed to write text report '{txt_path}': {exc}", command="report") from exc

    if fmt in {"pdf", "both"}:
        pdf_path = output_directory / f"{base_name}_report_{timestamp}.pdf"
        success, pdf_msg = services.report.generate_pdf_report(
            metadata, file_path_text, str(pdf_path), risk_analysis=analysis.to_dict()
        )
        if success:
            outputs.append(pdf_path)
            logger.info("Generated PDF report: %s", pdf_path)
        else:
            raise CLIReportError(f"Failed to generate PDF report: {pdf_msg}", command="report")

    _emit_header(state)
    print_success("Report generation completed")
    preview_lines = [_preview_report_text(text_report)]
    if record:
        preview_lines.insert(0, f"Record ID: {record.get('id')}")
    preview_lines.insert(0, f"Source: {file_path_text}")
    console.print(summary_panel("Report Preview", preview_lines, style="bright_cyan"))
    console.print(summary_panel("Saved Reports", [str(path) for path in outputs], style="green"))
    return EXIT_SUCCESS


def _handle_export(
    format_name: str,
    *,
    output: str | None = None,
    query: str = "",
    file_type: str = "All",
    date_filter: str = "All Time",
    sort: str = "Date (Newest)",
    limit: int = 0,
    state: CLIState,
) -> int:
    services = get_services(state)
    logger.info("Export command invoked (format=%s, output=%s, limit=%s)", format_name, output, limit)

    format_normalized = (format_name or "").strip().lower()
    default_suffix = {
        "json": ".json",
        "xml": ".xml",
        "csv": ".csv",
        "excel": ".xlsx",
        "pdf": ".pdf",
    }.get(format_normalized)
    if not default_suffix:
        raise CLIValidationError(
            f"Unsupported export format '{format_name}'. Choose from: json, xml, csv, excel, pdf.",
            command="export",
        )

    try:
        rows = _history_rows(limit=limit or 0, query=query, file_type=file_type, date_filter=date_filter, sort=sort)
    except Exception as exc:
        raise CLIDatabaseError(f"Database query failed during export: {exc}", command="export") from exc

    if not rows:
        raise CLIDatabaseError("No records matched the selected export filters.", command="export")

    dataframe = pd.DataFrame(
        rows,
        columns=[
            "ID",
            "File Path",
            "File Name",
            "File Size",
            "File Type",
            "Extracted At",
            "Modified On",
            "Full Metadata",
        ],
    )

    if output:
        output_path = Path(output).expanduser()
    else:
        output_path = PROJECT_ROOT / f"metadata_export_{_default_timestamp()}{default_suffix}"

    if output_path.suffix.lower() != default_suffix:
        output_path = output_path.with_suffix(default_suffix)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        ok, err_msg = services.report.export_records_dataframe(dataframe, format_normalized, str(output_path))
        if not ok:
            raise CLIReportError(err_msg, command="export")
        logger.info("Export completed successfully: %d records exported to %s", len(dataframe), output_path)
    except CLIError:
        raise
    except Exception as exc:
        raise CLIReportError(f"Export failed: {exc}", command="export") from exc

    _emit_header(state)
    print_success("Export completed")
    console.print(summary_panel("Export Complete", [f"Rows exported: {len(dataframe)}", f"Output: {output_path}"], style="green"))
    return EXIT_SUCCESS


def _handle_analytics(
    *,
    query: str = "",
    file_type: str = "all",
    date_range: str = "all",
    state: CLIState,
) -> int:
    services = get_services(state)
    try:
        summary = services.analytics.get_dashboard_metrics(
            date_range=date_range,
            file_type=file_type,
            search_query=query,
        )
    except Exception as exc:
        raise CLIDatabaseError(f"Failed to compute analytics: {exc}", command="analytics") from exc

    _emit_header(state)
    print_success("Analytics summary generated")
    console.print(
        summary_panel(
            "TraceLens Analytics Dashboard",
            [
                f"Total Analyzed Files: {summary.total_files}",
                f"Total Storage Volume: {summary.total_size_formatted}",
                f"Average File Size: {summary.avg_size_formatted}",
                f"Average Risk Score: {summary.avg_risk_score}/100",
            ],
            style="bright_cyan",
        )
    )

    risk_lines = [
        f"HIGH: {summary.risk_distribution.get('HIGH', 0)}",
        f"MEDIUM: {summary.risk_distribution.get('MEDIUM', 0)}",
        f"LOW: {summary.risk_distribution.get('LOW', 0)}",
    ]
    console.print(
        summary_panel(
            "Privacy Risk Breakdown",
            risk_lines,
            style="yellow" if summary.risk_distribution.get("HIGH", 0) > 0 else "green",
        )
    )

    if summary.file_type_counts:
        type_lines = [
            f"{ftype}: {count}"
            for ftype, count in sorted(summary.file_type_counts.items(), key=lambda x: x[1], reverse=True)
        ]
        console.print(summary_panel("File Type Distribution", type_lines, style="cyan"))

    if summary.top_threats:
        threat_lines = [f"- {t.get('reason', '')} ({t.get('count', 0)} occurrences)" for t in summary.top_threats]
        console.print(summary_panel("Top Discovered Threats", threat_lines, style="red"))
    return EXIT_SUCCESS


def _handle_history_list(
    *,
    limit: int = 10,
    query: str = "",
    file_type: str = "All",
    date_filter: str = "All Time",
    sort: str = "Date (Newest)",
    state: CLIState,
) -> int:
    if limit <= 0:
        raise CLIValidationError("Limit must be a positive integer.", command="history")
    try:
        rows = _history_rows(limit=limit, query=query, file_type=file_type, date_filter=date_filter, sort=sort)
    except Exception as exc:
        raise CLIDatabaseError(f"Failed to fetch history records: {exc}", command="history") from exc

    _emit_header(state)
    display_rows = [_row_to_record(row) for row in rows]
    _summarize_history_rows(display_rows, title="Recent History")
    return EXIT_SUCCESS


def _handle_history_delete(record_id_raw: str | int, *, yes: bool = False, state: CLIState) -> int:
    record_id = validate_record_id(record_id_raw)
    services = get_services(state)
    if not yes:
        reply = input(f"Delete history record {record_id}? [y/N]: ").strip().lower()
        if reply not in {"y", "yes"}:
            raise CLIError("Operation cancelled by user.", command="history", exit_code=ExitCode.GENERAL_ERROR)

    if services.history.delete_record(record_id):
        _emit_header(state)
        print_success(f"Deleted record ID {record_id}")
        console.print(summary_panel("History Updated", [f"Deleted record ID {record_id}"], style="green"))
        return EXIT_SUCCESS

    raise CLIDatabaseError(f"Record {record_id} was not found.", command="history")


def _handle_history_clear(*, yes: bool = False, state: CLIState) -> int:
    services = get_services(state)
    if not yes:
        reply = input("Clear all metadata history? [y/N]: ").strip().lower()
        if reply not in {"y", "yes"}:
            raise CLIError("Operation cancelled by user.", command="history", exit_code=ExitCode.GENERAL_ERROR)

    if services.history.clear_history():
        _emit_header(state)
        print_success("All metadata records were removed from the database.")
        console.print(
            summary_panel(
                "History Cleared",
                ["All metadata records were removed from the database."],
                style="green",
            )
        )
        return EXIT_SUCCESS

    raise CLIDatabaseError("Failed to clear metadata history.", command="history")


def _handle_history_stats(*, state: CLIState) -> int:
    services = get_services(state)
    try:
        stats = services.history.get_database_stats()
    except Exception as exc:
        raise CLIDatabaseError(f"Failed to retrieve database statistics: {exc}", command="history") from exc

    file_types = stats.get("file_types", {}) or {}
    _emit_header(state)
    print_success("Database statistics retrieved")
    console.print(
        summary_panel(
            "Database Statistics",
            [f"Total Records: {stats.get('total_records', 0)}"]
            + [f"{key or 'unknown'}: {value}" for key, value in file_types.items()],
            style="bright_cyan",
        )
    )
    return EXIT_SUCCESS


def _handle_config_show(*, state: CLIState) -> int:
    services = get_services(state)
    db_path = Path(services.database.db_path)
    log_file_path = get_log_file_path()
    _emit_header(state)
    console.print(
        summary_panel(
            "Configuration",
            [
                f"Version: {APP_VERSION}",
                f"Project root: {PROJECT_ROOT}",
                f"Database path: {db_path}",
                f"Log file path: {log_file_path}",
                f"Python: {sys.executable}",
                f"TRACELENS_DB_PATH: {os.getenv('TRACELENS_DB_PATH', '<not set>')}",
                f"TRACELENS_LOG_LEVEL: {os.getenv('TRACELENS_LOG_LEVEL', '<not set>')}",
            ],
            style="bright_cyan",
        )
    )
    return EXIT_SUCCESS


def _handle_config_optimize(*, state: CLIState) -> int:
    services = get_services(state)
    res = services.history.optimize_database()
    if isinstance(res, tuple):
        success, msg = res
    else:
        success, msg = bool(res), "Optimization completed"
    if success:
        _emit_header(state)
        print_success(f"SQLite optimization completed: {msg}")
        console.print(summary_panel("Configuration", [f"SQLite optimization completed: {msg}"], style="green"))
        return EXIT_SUCCESS
    raise CLIDatabaseError(f"Failed to optimize the database: {msg}", command="config")


def _handle_logs(
    *,
    lines: int = 50,
    clear: bool = False,
    path: bool = False,
    state: CLIState,
) -> int:
    log_path = get_log_file_path()
    if path:
        print(str(log_path))
        return EXIT_SUCCESS

    _emit_header(state)
    if clear:
        logger.info("Clearing logs via CLI command.")
        if clear_logs():
            print_success("Log buffer and file cleared.")
            console.print(summary_panel("Logs", ["Log buffer and file cleared."], style="green"))
            return EXIT_SUCCESS
        raise CLIFileError("Failed to clear log file.", command="logs")

    recent = get_recent_logs(max_entries=lines)
    if not recent:
        console.print(
            summary_panel(
                "TraceLens Logs",
                [f"Log file: {log_path}", "No log entries found in buffer or file."],
                style="yellow",
            )
        )
        return EXIT_SUCCESS

    console.print(
        summary_panel(
            "TraceLens Logs",
            [f"Log file: {log_path}", f"Showing last {len(recent)} entries:"] + recent,
            style="bright_cyan",
        )
    )
    return EXIT_SUCCESS


# ==============================================================================
# Single Canonical Help & Command Metadata Source
# ==============================================================================

HELP_TOPICS: dict[str, dict[str, Any]] = {
    "extract": {
        "is_command": True,
        "title": "Metadata Extraction & Ingestion",
        "phase": "1. Ingest",
        "table_desc": "Extract metadata from file(s) and store in database",
        "summary": "Extract raw metadata properties from files and store records in SQLite history.",
        "syntax": "tracelens extract <targets...> [OPTIONS]",
        "arguments": [
            ("<targets...>", "One or more file paths to inspect."),
        ],
        "options": [
            ("--no-save", "Extract and display metadata without storing in the SQLite database."),
            ("--details", "Display the full metadata key-value table in addition to the summary."),
            ("--recursive / --flat", "Scan subdirectories when used with batch mode."),
        ],
        "examples": [
            "tracelens extract photo.jpg",
            "tracelens extract document.pdf --no-save",
            "tracelens -v extract sample.jpg",
        ],
        "flow": "Ingests metadata into the database. Run 'tracelens analyze <file>' next to audit privacy risks, or 'tracelens report <id>' to generate documentation.",
        "related": ["analyze", "report", "batch", "search"],
    },
    "batch": {
        "is_command": True,
        "title": "Batch Directory Processing",
        "phase": "1. Ingest",
        "table_desc": "Batch process all files in a folder with progress",
        "summary": "Process all files in a directory with per-file progress and risk aggregation.",
        "syntax": "tracelens batch <directory> [OPTIONS]",
        "arguments": [
            ("<directory>", "Directory path to scan and extract."),
        ],
        "options": [
            ("--recursive / --flat", "Scan subdirectories recursively (default: --recursive)."),
            ("--no-save", "Extract without storing records in the database."),
        ],
        "examples": [
            "tracelens batch ./samples",
            "tracelens batch ./evidence --flat --no-save",
        ],
        "flow": "Processes an entire folder of files resiliently, reporting per-file progress and a final summary.",
        "related": ["extract", "analyze", "report"],
    },
    "analyze": {
        "is_command": True,
        "title": "Privacy & Forensic Risk Analysis",
        "phase": "2. Audit",
        "table_desc": "Audit privacy risks, scores (0-100), and event timelines",
        "summary": "Run rule-based privacy assessments on metadata to identify sensitive leaks and forensic timelines.",
        "syntax": "tracelens analyze <targets...> [OPTIONS]",
        "arguments": [
            ("<targets...>", "One or more file or directory paths to analyze."),
        ],
        "options": [
            ("--threshold <int>", "Filter and display only files exceeding a specific risk score (0-100)."),
            ("--no-save", "Perform risk analysis without storing extraction records."),
            ("--recursive / --flat", "Scan directories recursively (default: --recursive)."),
        ],
        "examples": [
            "tracelens analyze document.pdf",
            "tracelens analyze ./evidence/ --threshold 50",
            "tracelens analyze photo.jpg --no-save",
        ],
        "flow": "Calculates risk scores (0-100), risk levels (LOW/MEDIUM/HIGH), matched security rules (GPS, camera serials, author identities), and forensic timelines. If risks are detected, run 'tracelens sanitize <file>'.",
        "related": ["extract", "sanitize", "report"],
    },
    "sanitize": {
        "is_command": True,
        "title": "Metadata Stripping & Privacy Redaction",
        "phase": "3. Remediate",
        "table_desc": "Strip sensitive metadata tags (GPS, author, serials)",
        "summary": "Remove identifying metadata tags (EXIF, GPS coordinates, author, camera serials) from files.",
        "syntax": "tracelens sanitize <targets...> [OPTIONS]",
        "arguments": [
            ("<targets...>", "Files or folders containing files to sanitize."),
        ],
        "options": [
            ("--dry-run", "Preview which metadata tags would be removed without modifying files."),
            ("--backup / --no-backup", "Create a .bak copy of original files before stripping (default: backup enabled)."),
            ("--recursive / --flat", "Recursively sanitize files in directories (default: --recursive)."),
        ],
        "examples": [
            "tracelens sanitize photo.jpg",
            "tracelens sanitize ./public_release/ --dry-run",
            "tracelens sanitize document.pdf --no-backup",
        ],
        "flow": "Strips sensitive metadata tags so files are safe to share publicly. Follow up with 'tracelens analyze <file>' to verify risk score is reduced to 0.",
        "related": ["analyze", "edit", "extract"],
    },
    "edit": {
        "is_command": True,
        "title": "Metadata Field Editing & Anonymization",
        "phase": "3. Remediate",
        "table_desc": "Update or anonymize specific metadata keys",
        "summary": "Update, replace, or insert specific metadata keys into a file and/or database record.",
        "syntax": "tracelens edit <source> [OPTIONS]",
        "arguments": [
            ("<source>", "Target file path."),
        ],
        "options": [
            ("-s, --set KEY=VALUE", "Set or overwrite a metadata field (e.g. -s Author=\"Redacted\"). Can repeat."),
            ("--metadata-file <path>", "JSON file containing metadata key-value pairs to merge."),
            ("--write-file / --no-write-file", "Persist metadata changes to the physical file on disk (default: enabled)."),
            ("--save-db / --no-save-db", "Save changes to the SQLite metadata database (default: enabled)."),
        ],
        "examples": [
            "tracelens edit doc.pdf -s Author='Anon'",
            "tracelens edit document.pdf -s Author=\"Anonymous\" -s Company=\"Confidential\"",
            "tracelens edit sample.docx --metadata-file updates.json",
        ],
        "flow": "Allows surgical modification or anonymization of specific metadata attributes without full stripping.",
        "related": ["sanitize", "report", "history"],
    },
    "report": {
        "is_command": True,
        "title": "Comprehensive Audit & Forensic Reporting",
        "phase": "4. Document",
        "table_desc": "Generate structured TXT & publication-ready PDF reports",
        "summary": "Generate formal plain-text (.txt) and publication-ready PDF (.pdf) audit reports.",
        "syntax": "tracelens report <source> [OPTIONS]",
        "arguments": [
            ("<source>", "Database history record ID (integer) OR target file path."),
        ],
        "options": [
            ("-f, --format [txt|pdf|both]", "Report output format (default: both)."),
            ("--output-dir <path>", "Directory where report files will be written (default: current directory)."),
        ],
        "examples": [
            "tracelens report 17 --format both",
            "tracelens report evidence.pdf",
            "tracelens report document.docx --format pdf --output-dir ./audit_reports",
        ],
        "flow": "Generates complete documentation including metadata tables, privacy risk evaluations, matched rules, and forensic timelines.",
        "related": ["extract", "analyze", "export"],
    },
    "export": {
        "is_command": True,
        "title": "Structured Dataset Export",
        "phase": "4. Document",
        "table_desc": "Export history dataset to JSON, CSV, XML, Excel, or PDF",
        "summary": "Export filtered database history to industry-standard data formats.",
        "syntax": "tracelens export <format> [OPTIONS]",
        "arguments": [
            ("<format>", "Export format: json, csv, xml, excel, or pdf."),
        ],
        "options": [
            ("-o, --output <path>", "Destination file path for the exported dataset."),
            ("--query <text>", "Filter records by matching text in file name or file path."),
            ("--file-type <ext>", "Filter by file extension (e.g. pdf, jpg, docx, All)."),
            ("--date-filter <period>", "Filter by time: 'All Time', 'Today', 'This Week', 'This Month', 'Last 30 Days'."),
            ("--sort <order>", "Sort order: 'Date (Newest)', 'Date (Oldest)', 'Name (A-Z)'."),
            ("--limit <int>", "Maximum records to export (0 = unlimited)."),
        ],
        "examples": [
            "tracelens export json -o out.json",
            "tracelens export excel --file-type pdf --query \"contract\"",
            "tracelens export csv --limit 100",
        ],
        "flow": "Produces portable audit trails for compliance, external analysis in spreadsheets, or ingestion into external tools.",
        "related": ["report", "history", "analytics"],
    },
    "search": {
        "is_command": True,
        "title": "Database Metadata Search",
        "phase": "5. Monitor",
        "table_desc": "Search historical metadata records by keyword query",
        "summary": "Search historical metadata extraction records by keyword query.",
        "syntax": "tracelens search <query> [OPTIONS]",
        "arguments": [
            ("<query>", "Non-empty keyword query to match against file names or paths."),
        ],
        "options": [
            ("--file-type <ext>", "Filter by file extension (e.g. pdf, jpg, All)."),
            ("--date-filter <period>", "Filter by time range (All Time, Today, This Week, This Month, Last 30 Days)."),
            ("--sort <order>", "Sort order (Date (Newest), Date (Oldest), Name (A-Z))."),
            ("--limit <int>", "Maximum matching records to display (default: 20)."),
        ],
        "examples": [
            "tracelens search confidential",
            "tracelens search invoice --file-type pdf --limit 10",
        ],
        "flow": "Quickly locate previously extracted files and pass their Record ID to 'tracelens report <id>'.",
        "related": ["history", "report", "export"],
    },
    "history": {
        "is_command": True,
        "title": "History Record Management & Inspection",
        "phase": "5. Monitor",
        "table_desc": "Search, inspect, delete, or clear scan history",
        "summary": "Search, inspect, delete, and manage historical metadata extraction records.",
        "syntax": "tracelens history [SUBCOMMAND] [OPTIONS]",
        "arguments": [
            ("[SUBCOMMAND]", "Optional subcommand: delete, clear, stats (default: list records)."),
        ],
        "options": [
            ("--limit <int>", "Number of records to display (default: 10)."),
            ("--query <text>", "Filter history by file name or path search."),
            ("--file-type <ext>", "Filter by file extension."),
            ("--date-filter <period>", "Filter by date range."),
            ("--sort <order>", "Sort order."),
            ("delete <id> [--yes]", "Delete a specific record by ID."),
            ("clear [--yes]", "Delete all historical records from the database."),
            ("stats", "Display total record counts grouped by file type."),
        ],
        "examples": [
            "tracelens history --query 'secret'",
            "tracelens history --limit 50 --query \"evidence\"",
            "tracelens history delete 142 --yes",
            "tracelens history stats",
        ],
        "flow": "Query past investigations and reuse historical record IDs directly with 'tracelens report <id>'.",
        "related": ["search", "report", "edit", "analytics"],
    },
    "analytics": {
        "is_command": True,
        "title": "Dashboard Metrics & Aggregate Intelligence",
        "phase": "5. Monitor",
        "table_desc": "Show intelligence metrics, risk distribution, trends",
        "summary": "Compute and display aggregate metadata analytics, privacy risk metrics, and trends.",
        "syntax": "tracelens analytics [OPTIONS]",
        "arguments": [],
        "options": [
            ("--date-range <range>", "Date filter: all, today, week, month, year (default: all)."),
            ("--file-type <ext>", "Filter metrics by file extension (default: all)."),
            ("--query <text>", "Filter analytics by text search."),
        ],
        "examples": [
            "tracelens analytics --date-range month",
            "tracelens analytics --file-type pdf",
        ],
        "flow": "Provides an executive summary of dataset health, risk score distribution (LOW/MED/HIGH), top risk factors, and file types.",
        "related": ["history", "export"],
    },
    "config": {
        "is_command": True,
        "title": "Environment & Database Configuration",
        "phase": "Utility",
        "table_desc": "View environment config or optimize SQLite database",
        "summary": "Inspect active configuration paths and optimize the SQLite database.",
        "syntax": "tracelens config [optimize]",
        "arguments": [
            ("[optimize]", "Optional subcommand: optimize SQLite storage."),
        ],
        "options": [
            ("optimize", "Perform SQLite VACUUM/ANALYZE optimization to improve query performance."),
        ],
        "examples": [
            "tracelens config optimize",
            "tracelens config",
        ],
        "flow": "Use 'optimize' periodically after large batch scans or record deletions.",
        "related": ["logs", "history"],
    },
    "logs": {
        "is_command": True,
        "title": "Application Execution Logs",
        "phase": "Utility",
        "table_desc": "Inspect, view path, or clear application logs",
        "summary": "Inspect recent log messages, check log file path, or clear log buffer.",
        "syntax": "tracelens logs [OPTIONS]",
        "arguments": [],
        "options": [
            ("-n, --lines <int>", "Number of recent log lines to display (default: 50)."),
            ("-p, --path", "Print absolute path to the active log file."),
            ("--clear", "Clear log file on disk and in-memory log buffer."),
        ],
        "examples": [
            "tracelens logs -n 50",
            "tracelens logs --path",
            "tracelens logs --clear",
        ],
        "flow": "Helps troubleshoot unsupported formats, extraction warnings, or database connectivity issues.",
        "related": ["config"],
    },
    "help": {
        "is_command": True,
        "title": "CLI Workflow & Command Reference Guide",
        "phase": "Utility",
        "table_desc": "Display full workflow guide or topic-specific help",
        "summary": "Display the canonical TraceLens CLI workflow pipeline, command table, and topic guides.",
        "syntax": "tracelens help [COMMAND]",
        "arguments": [
            ("[COMMAND]", "Optional command or topic name (e.g. extract, analyze, report, workflow)."),
        ],
        "options": [],
        "examples": [
            "tracelens help",
            "tracelens help extract",
            "tracelens help workflow",
        ],
        "flow": "Provides both an end-to-end operational overview and deep-dive command documentation.",
        "related": ["extract", "analyze", "report", "batch"],
    },
    "workflow": {
        "is_command": False,
        "title": "TraceLens End-to-End Pipeline & Workflows",
        "phase": "Overview",
        "table_desc": "Detailed walkthrough of end-to-end operational workflows",
        "summary": "Detailed walkthrough of how TraceLens commands connect into end-to-end operational workflows.",
        "syntax": "tracelens help workflow",
        "arguments": [],
        "options": [],
        "examples": [
            "tracelens help workflow",
            "tracelens help extract",
            "tracelens help sanitize",
        ],
        "flow": "Explains the Ingest -> Audit -> Remediate -> Document -> Monitor lifecycle.",
        "related": ["extract", "analyze", "sanitize", "report", "history"],
    },
}


def _render_workflow_panel() -> Panel:
    """Build the visual pipeline architecture diagram."""
    lines = [
        "[bold cyan]STAGE 1: INGEST[/bold cyan]       [white]tracelens extract <file>[/white]          Scan & persist metadata to SQLite",
        "                     [white]tracelens batch <directory>[/white]       Batch process an entire directory",
        "      |",
        "      v",
        "[bold yellow]STAGE 2: AUDIT[/bold yellow]        [white]tracelens analyze <file>[/white]          Evaluate privacy score (0-100) & leaks",
        "      |",
        "      v",
        "[bold red]STAGE 3: REMEDIATE[/bold red]   [white]tracelens sanitize <targets>[/white]      Strip sensitive tags (EXIF/GPS/Device)",
        "                     [white]tracelens edit <file> -s K=V[/white]      Surgically edit or anonymize attributes",
        "      |",
        "      v",
        "[bold magenta]STAGE 4: DOCUMENT[/bold magenta]    [white]tracelens report <id_or_file>[/white]     Create formatted PDF & TXT audit reports",
        "                     [white]tracelens export <format>[/white]         Export dataset to JSON, CSV, or Excel",
        "      |",
        "      v",
        "[bold green]STAGE 5: MONITOR[/bold green]     [white]tracelens search <query>[/white]          Search historical records by keyword",
        "                     [white]tracelens history[/white]                 Inspect & manage past scans",
        "                     [white]tracelens analytics[/white]               View risk distributions & metrics",
    ]
    return Panel(
        "\n".join(lines),
        title="TraceLens CLI Workflow Pipeline",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _render_command_table() -> Table:
    """Build the master command reference table from the canonical `HELP_TOPICS` definitions."""
    table = Table(
        title="Command Reference",
        box=box.ROUNDED,
        show_lines=False,
        header_style="bold bright_cyan",
    )
    table.add_column("Command", style="bold cyan", no_wrap=True)
    table.add_column("Phase", style="yellow", no_wrap=True)
    table.add_column("Description", style="white", overflow="fold")
    table.add_column("Example Usage", style="green", no_wrap=False)

    for cmd_name, info in HELP_TOPICS.items():
        if not info.get("is_command", False):
            continue
        examples = info.get("examples") or [f"tracelens {cmd_name}"]
        table.add_row(
            cmd_name,
            info["phase"],
            info.get("table_desc", info["summary"]),
            examples[0],
        )
    return table


def _render_scenarios_panel() -> Panel:
    """Build the common operational workflows panel."""
    scenarios = [
        "[bold cyan]1. Pre-Publication Privacy Sanitization[/bold cyan] (Strip metadata before sharing):",
        "   [white]tracelens extract photo.jpg[/white]   ->   [white]tracelens analyze photo.jpg[/white]   ->   [green]tracelens sanitize photo.jpg[/green]",
        "",
        "[bold cyan]2. Forensic Evidence Audit & PDF Reporting[/bold cyan] (Document file history):",
        "   [white]tracelens batch ./evidence/[/white]   ->   [white]tracelens analyze ./evidence/ --threshold 50[/white] ->   [green]tracelens report 17 --format both[/green]",
        "",
        "[bold cyan]3. Compliance Auditing & Structured Export[/bold cyan] (Export records for auditing):",
        "   [white]tracelens search 'confidential'[/white] ->   [green]tracelens export excel --output audit.xlsx[/green]",
    ]
    return Panel(
        "\n".join(scenarios),
        title="Common Operational Workflows",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _display_topic_help(topic: str) -> None:
    """Display deep-dive help for a specific command or topic from `HELP_TOPICS`."""
    info = HELP_TOPICS.get(topic)
    if not info:
        console.print(
            summary_panel(
                "Unknown Command or Topic",
                [
                    f"No dedicated help topic found matching '{topic}'.",
                    f"Available topics: {', '.join(sorted(HELP_TOPICS.keys()))}",
                ],
                style="yellow",
            )
        )
        render_full_help(include_header=False)
        return

    overview_lines = [
        f"[bold]Phase:[/bold] {info['phase']}",
        f"[bold]Purpose:[/bold] {info['summary']}",
        "",
        f"[bold]Workflow Role:[/bold] {info['flow']}",
    ]
    console.print(summary_panel(f"Command Guide: tracelens {topic}", overview_lines, style="bright_cyan"))
    console.print(summary_panel("Syntax", [info["syntax"]], style="cyan"))

    args = info.get("arguments", [])
    opts = info.get("options", [])
    if args or opts:
        table = Table(title=f"Options & Parameters for '{topic}'", box=box.ROUNDED, header_style="bold bright_cyan")
        table.add_column("Parameter / Flag", style="bold cyan", no_wrap=True)
        table.add_column("Description", style="white", overflow="fold")
        for arg_name, arg_desc in args:
            table.add_row(arg_name, arg_desc)
        for opt_name, opt_desc in opts:
            table.add_row(opt_name, opt_desc)
        console.print(table)

    examples = info.get("examples", [])
    if examples:
        console.print(summary_panel("Examples", examples, style="green"))

    related = info.get("related", [])
    if related:
        related_str = ", ".join(f"[bold cyan]tracelens help {r}[/bold cyan]" for r in related)
        console.print(f"[dim]Related commands: {related_str}[/dim]\n")


def render_full_help(
    topic: str | None = None,
    *,
    state: CLIState | None = None,
    include_header: bool = True,
) -> None:
    """Single canonical help renderer used by both `tracelens help` and `tracelens --help`."""
    if include_header:
        _emit_header(state)

    if topic:
        _display_topic_help(topic.strip().lower())
        return

    print("usage: tracelens [-h] [-v] [-q] [--db-path PATH] [-V] COMMAND ...")
    console.print(_render_workflow_panel())
    console.print(_render_command_table())
    console.print(_render_scenarios_panel())
    console.print(
        "[dim]Global Options: -h/--help, -V/--version, -v/--verbose, -q/--quiet, --db-path PATH[/dim]\n"
        "[dim]Tip: Run [bold cyan]tracelens <command> --help[/bold cyan] or [bold cyan]tracelens help <command>[/bold cyan] for in-depth flags, options, and examples.[/dim]\n"
    )


# ==============================================================================
# Argparse Implementation (build_parser & centralized error handling)
# ==============================================================================


class _ParserSignal(Exception):
    """Internal control-flow signal raised when argparse exits early (--help, --version, or parse error)."""

    def __init__(self, exit_code: int) -> None:
        super().__init__(exit_code)
        self.exit_code = exit_code


class TraceLensArgumentParser(argparse.ArgumentParser):
    """Custom ArgumentParser providing canonical help rendering, error formatting, and exit codes."""

    def __init__(self, *args: Any, command_label: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.command_label = command_label

    def print_help(self, file: Any = None) -> None:
        if self.command_label is None:
            render_full_help()
            return
        super().print_help(file=file)

    def error(self, message_text: str) -> None:
        cmd = self.command_label
        hint = (
            f"Use 'tracelens {cmd} --help' for usage information."
            if cmd
            else "Use 'tracelens --help' for usage information."
        )
        print_error(f"Invalid command or argument: {message_text}", hint=hint)
        raise _ParserSignal(EXIT_INVALID_ARGS)

    def exit(self, status: int = 0, message_text: str | None = None) -> None:
        if message_text:
            print(message_text, end="")
        raise _ParserSignal(status)


def _add_shared_global_options(parser: argparse.ArgumentParser, *, is_root: bool = False) -> None:
    """Add global options (-v/--verbose, -q/--quiet, --db-path) to root or subcommand parser."""
    default_bool: Any = False if is_root else argparse.SUPPRESS
    default_none: Any = None if is_root else argparse.SUPPRESS

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=default_bool,
        help="Enable verbose diagnostic logging (INFO/DEBUG).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=default_bool,
        help="Suppress banners and non-essential output.",
    )
    parser.add_argument(
        "--db-path",
        dest="db_path",
        default=default_none,
        metavar="PATH",
        help="Custom SQLite database path to use.",
    )


def _add_canonical_subparser(
    subparsers: Any,
    command_name: str,
    *,
    parents: list[argparse.ArgumentParser],
) -> TraceLensArgumentParser:
    """Create a subparser populated from the canonical `HELP_TOPICS` source of truth."""
    info = HELP_TOPICS[command_name]
    examples = info.get("examples", [])
    epilog = ("Examples:\n  " + "\n  ".join(examples)) if examples else None
    return subparsers.add_parser(
        command_name,
        parents=parents,
        command_label=command_name,
        help=info.get("table_desc", info["summary"]),
        description=info["summary"],
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def build_parser() -> TraceLensArgumentParser:
    """Construct and return the main TraceLens `argparse.ArgumentParser` with subparsers."""
    shared_parent = argparse.ArgumentParser(add_help=False)
    _add_shared_global_options(shared_parent, is_root=False)

    parser = TraceLensArgumentParser(
        prog="tracelens",
        description="TraceLens: Digital forensics and metadata analysis toolkit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_shared_global_options(parser, is_root=True)
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"TraceLens {APP_VERSION}",
        help="Show program's version number and exit.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="Commands",
        metavar="COMMAND",
        parser_class=TraceLensArgumentParser,
        help="Available TraceLens commands (run 'tracelens <command> --help' for details).",
    )

    # 1. extract
    extract_parser = _add_canonical_subparser(subparsers, "extract", parents=[shared_parent])
    extract_parser.add_argument(
        "targets",
        nargs="+",
        metavar="FILE",
        help="File path(s) from which to extract metadata.",
    )
    extract_parser.add_argument(
        "--no-save",
        action="store_true",
        default=False,
        help="Extract metadata without saving results to the database.",
    )
    extract_parser.add_argument(
        "--details",
        "--full",
        dest="details",
        action="store_true",
        default=False,
        help="Display the full extracted metadata key-value table.",
    )
    extract_parser.add_argument(
        "--recursive",
        dest="recursive",
        action="store_true",
        default=False,
        help="Scan directories recursively.",
    )
    extract_parser.add_argument(
        "--flat",
        dest="recursive",
        action="store_false",
        help="Disable recursive scanning.",
    )

    # 2. batch
    batch_parser = _add_canonical_subparser(subparsers, "batch", parents=[shared_parent])
    batch_parser.add_argument(
        "directory",
        metavar="DIRECTORY",
        help="Path to the directory to process in batch.",
    )
    batch_parser.add_argument(
        "--recursive",
        dest="recursive",
        action="store_true",
        default=True,
        help="Scan directory recursively (default).",
    )
    batch_parser.add_argument(
        "--flat",
        dest="recursive",
        action="store_false",
        help="Only process files in the top-level directory.",
    )
    batch_parser.add_argument(
        "--no-save",
        action="store_true",
        default=False,
        help="Extract metadata without saving records to the database.",
    )

    # 3. analyze
    analyze_parser = _add_canonical_subparser(subparsers, "analyze", parents=[shared_parent])
    analyze_parser.add_argument(
        "targets",
        nargs="+",
        metavar="FILE",
        help="One or more files or directories to analyze.",
    )
    analyze_parser.add_argument(
        "--recursive",
        dest="recursive",
        action="store_true",
        default=True,
        help="Scan folders recursively (default).",
    )
    analyze_parser.add_argument(
        "--flat",
        dest="recursive",
        action="store_false",
        help="Scan only top-level files in folders.",
    )
    analyze_parser.add_argument(
        "--threshold",
        type=int,
        default=0,
        metavar="SCORE",
        help="Minimum risk score threshold (0-100) to include in results.",
    )
    analyze_parser.add_argument(
        "--no-save",
        action="store_true",
        default=True,
        help="Do not persist extracted metadata during risk analysis.",
    )

    # 4. sanitize
    sanitize_parser = _add_canonical_subparser(subparsers, "sanitize", parents=[shared_parent])
    sanitize_parser.add_argument(
        "targets",
        nargs="+",
        metavar="TARGET",
        help="One or more files or folders to sanitize.",
    )
    sanitize_parser.add_argument(
        "--backup",
        dest="backup",
        action="store_true",
        default=True,
        help="Create a .bak backup file before sanitizing (default).",
    )
    sanitize_parser.add_argument(
        "--no-backup",
        dest="backup",
        action="store_false",
        help="Do not create a .bak backup file.",
    )
    sanitize_parser.add_argument(
        "--recursive",
        dest="recursive",
        action="store_true",
        default=True,
        help="Scan folders recursively (default).",
    )
    sanitize_parser.add_argument(
        "--flat",
        dest="recursive",
        action="store_false",
        help="Scan folders non-recursively.",
    )
    sanitize_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview sanitization without modifying files.",
    )

    # 5. edit
    edit_parser = _add_canonical_subparser(subparsers, "edit", parents=[shared_parent])
    edit_parser.add_argument(
        "file_path",
        metavar="FILE",
        help="File whose metadata should be updated.",
    )
    edit_parser.add_argument(
        "-s",
        "--set",
        dest="set_values",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Metadata field update in KEY=VALUE form (can be specified multiple times).",
    )
    edit_parser.add_argument(
        "--metadata-file",
        default=None,
        metavar="JSON_FILE",
        help="Path to a JSON file containing metadata fields to merge.",
    )
    edit_parser.add_argument(
        "--write-file",
        dest="write_file",
        action="store_true",
        default=True,
        help="Write changes back to the physical file when supported (default).",
    )
    edit_parser.add_argument(
        "--no-write-file",
        dest="write_file",
        action="store_false",
        help="Do not modify the physical file on disk.",
    )
    edit_parser.add_argument(
        "--save-db",
        dest="save_db",
        action="store_true",
        default=True,
        help="Save updated metadata to the SQLite database (default).",
    )
    edit_parser.add_argument(
        "--no-save-db",
        "--no-db",
        dest="save_db",
        action="store_false",
        help="Do not save updated metadata to the database.",
    )

    # 6. report
    report_parser = _add_canonical_subparser(subparsers, "report", parents=[shared_parent])
    report_parser.add_argument(
        "source",
        metavar="ID",
        help="Database record ID (integer) or target file path.",
    )
    report_parser.add_argument(
        "-f",
        "--format",
        dest="format_name",
        default="both",
        metavar="FORMAT",
        help="Output report format: txt, pdf, or both (default: both).",
    )
    report_parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT),
        metavar="DIR",
        help="Directory where generated report files should be saved.",
    )

    # 7. export
    export_parser = _add_canonical_subparser(subparsers, "export", parents=[shared_parent])
    export_parser.add_argument(
        "format_name",
        metavar="FORMAT",
        help="Export format: json, xml, csv, excel, or pdf.",
    )
    export_parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="PATH",
        help="Destination file path for exported records.",
    )
    export_parser.add_argument(
        "--query",
        default="",
        help="Text search across file name and file path.",
    )
    export_parser.add_argument(
        "--file-type",
        default="All",
        help="Filter by file type extension.",
    )
    export_parser.add_argument(
        "--date-filter",
        default="All Time",
        help="Filter by time period.",
    )
    export_parser.add_argument(
        "--sort",
        default="Date (Newest)",
        help="Sort order for the export set.",
    )
    export_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum records to export (0 means no limit).",
    )

    # 8. search
    search_parser = _add_canonical_subparser(subparsers, "search", parents=[shared_parent])
    search_parser.add_argument(
        "query",
        metavar="QUERY",
        help="Non-empty search query to match against file names and paths.",
    )
    search_parser.add_argument(
        "--file-type",
        default="All",
        metavar="TYPE",
        help="Filter by file extension (e.g. pdf, jpg, All).",
    )
    search_parser.add_argument(
        "--date-filter",
        default="All Time",
        metavar="PERIOD",
        help="Filter by time range ('All Time', 'Today', 'This Week', 'This Month', 'Last 30 Days').",
    )
    search_parser.add_argument(
        "--sort",
        default="Date (Newest)",
        metavar="ORDER",
        help="Sort order ('Date (Newest)', 'Date (Oldest)', 'Name (A-Z)').",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="Maximum number of records to display (default: 20).",
    )

    # 9. history
    history_parser = _add_canonical_subparser(subparsers, "history", parents=[shared_parent])
    history_parser.add_argument(
        "history_action",
        nargs="?",
        default=None,
        choices=["delete", "clear", "stats"],
        metavar="SUBCOMMAND",
        help="Optional history action: delete, clear, or stats.",
    )
    history_parser.add_argument(
        "record_id",
        nargs="?",
        default=None,
        metavar="ID",
        help="Record ID when using 'history delete <id>'.",
    )
    history_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of records to display (default: 10).",
    )
    history_parser.add_argument(
        "--query",
        default="",
        help="Text search across file name and file path.",
    )
    history_parser.add_argument(
        "--file-type",
        default="All",
        help="Filter by file type.",
    )
    history_parser.add_argument(
        "--date-filter",
        default="All Time",
        help="Filter by time period.",
    )
    history_parser.add_argument(
        "--sort",
        default="Date (Newest)",
        help="Sort order for displayed records.",
    )
    history_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Skip confirmation prompt for delete/clear.",
    )

    # 10. analytics
    analytics_parser = _add_canonical_subparser(subparsers, "analytics", parents=[shared_parent])
    analytics_parser.add_argument(
        "--query",
        default="",
        help="Filter analytics by text search.",
    )
    analytics_parser.add_argument(
        "--file-type",
        default="all",
        help="Filter by file type extension.",
    )
    analytics_parser.add_argument(
        "--date-range",
        default="all",
        help="Date filter: all, today, week, month, year.",
    )

    # 11. config
    config_parser = _add_canonical_subparser(subparsers, "config", parents=[shared_parent])
    config_parser.add_argument(
        "config_action",
        nargs="?",
        default=None,
        choices=["optimize"],
        metavar="SUBCOMMAND",
        help="Optional subcommand: optimize.",
    )

    # 12. logs
    logs_parser = _add_canonical_subparser(subparsers, "logs", parents=[shared_parent])
    logs_parser.add_argument(
        "-n",
        "--lines",
        type=int,
        default=50,
        help="Number of recent log lines to display (default: 50).",
    )
    logs_parser.add_argument(
        "--clear",
        action="store_true",
        default=False,
        help="Clear log file and in-memory buffer.",
    )
    logs_parser.add_argument(
        "-p",
        "--path",
        action="store_true",
        default=False,
        help="Print path to the active log file.",
    )

    # 13. help
    help_parser = _add_canonical_subparser(subparsers, "help", parents=[shared_parent])
    help_parser.add_argument(
        "command_name",
        nargs="?",
        default=None,
        metavar="COMMAND",
        help="Optional command name or topic (e.g. extract, analyze, search, report, batch).",
    )

    return parser


def _dispatch_parsed_args(ns: argparse.Namespace, state: CLIState) -> int:
    """Dispatch parsed argparse namespace to the corresponding command handler."""
    cmd = getattr(ns, "command", None)
    if cmd is None:
        _emit_header(state)
        console.print(
            summary_panel(
                "Quick Start",
                [
                    "tracelens help                # View complete CLI workflow & command guide",
                    "tracelens --help              # Display the same canonical CLI command guide",
                    "tracelens extract file.pdf    # Ingest metadata into database",
                    "tracelens analyze file.pdf    # Assess privacy risks & scores",
                    "tracelens search confidential # Search stored metadata records",
                    "tracelens report 12           # Generate TXT and PDF audit reports",
                    "tracelens batch ./samples     # Batch process all files in a folder",
                    "tracelens sanitize file.pdf   # Remove sensitive metadata tags",
                    "tracelens history             # Browse past extractions",
                    "tracelens analytics           # View dashboard intelligence",
                ],
                style="bright_cyan",
            )
        )
        return EXIT_SUCCESS

    if cmd == "extract":
        return _handle_extract(
            ns.targets,
            no_save=ns.no_save,
            recursive=ns.recursive,
            details=ns.details,
            state=state,
        )
    if cmd == "analyze":
        return _handle_analyze(
            ns.targets,
            recursive=ns.recursive,
            threshold=ns.threshold,
            no_save=ns.no_save,
            state=state,
        )
    if cmd == "search":
        return _handle_search(
            ns.query,
            file_type=ns.file_type,
            date_filter=ns.date_filter,
            sort=ns.sort,
            limit=ns.limit,
            state=state,
        )
    if cmd == "report":
        return _handle_report(
            ns.source,
            format_name=ns.format_name,
            output_dir=ns.output_dir,
            state=state,
        )
    if cmd == "batch":
        return _handle_batch(
            ns.directory,
            recursive=ns.recursive,
            no_save=ns.no_save,
            state=state,
        )
    if cmd == "sanitize":
        return _handle_sanitize(
            ns.targets,
            backup=ns.backup,
            recursive=ns.recursive,
            dry_run=ns.dry_run,
            state=state,
        )
    if cmd == "edit":
        return _handle_edit(
            ns.file_path,
            set_values=ns.set_values,
            metadata_file=ns.metadata_file,
            write_file=ns.write_file,
            save_db=ns.save_db,
            state=state,
        )
    if cmd == "export":
        return _handle_export(
            ns.format_name,
            output=ns.output,
            query=ns.query,
            file_type=ns.file_type,
            date_filter=ns.date_filter,
            sort=ns.sort,
            limit=ns.limit,
            state=state,
        )
    if cmd == "history":
        action = ns.history_action
        if action == "delete":
            if ns.record_id is None:
                raise CLIValidationError("Missing record ID for 'history delete'.", command="history")
            return _handle_history_delete(ns.record_id, yes=ns.yes, state=state)
        if action == "clear":
            return _handle_history_clear(yes=ns.yes, state=state)
        if action == "stats":
            return _handle_history_stats(state=state)
        return _handle_history_list(
            limit=ns.limit,
            query=ns.query,
            file_type=ns.file_type,
            date_filter=ns.date_filter,
            sort=ns.sort,
            state=state,
        )
    if cmd == "analytics":
        return _handle_analytics(
            query=ns.query,
            file_type=ns.file_type,
            date_range=ns.date_range,
            state=state,
        )
    if cmd == "config":
        if ns.config_action == "optimize":
            return _handle_config_optimize(state=state)
        return _handle_config_show(state=state)
    if cmd == "logs":
        return _handle_logs(lines=ns.lines, clear=ns.clear, path=ns.path, state=state)
    if cmd == "help":
        render_full_help(ns.command_name, state=state)
        return EXIT_SUCCESS

    raise CLIValidationError(f"Unknown command: {cmd}", exit_code=ExitCode.INVALID_ARGS)


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point using `argparse` and centralized error handling.

    Args:
        argv: Optional list of command-line arguments (defaults to `sys.argv[1:]`).

    Returns:
        int: Standardized exit status code (`ExitCode`).
    """
    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    try:
        ns = parser.parse_args(args_list)
    except _ParserSignal as sig:
        return int(sig.exit_code)

    verbose = bool(getattr(ns, "verbose", False))
    quiet = bool(getattr(ns, "quiet", False))
    db_path = getattr(ns, "db_path", None)
    command_name = getattr(ns, "command", None)

    state = _configure_session_state(verbose=verbose, quiet=quiet, db_path=db_path)

    def _verbose_console_listener(record: logging.LogRecord, _formatted: str) -> None:
        if record.levelno >= logging.DEBUG:
            print(f"[{record.levelname}] {record.getMessage()}")

    if verbose:
        add_log_listener(_verbose_console_listener)

    try:
        return _dispatch_parsed_args(ns, state)
    except _ParserSignal as sig:
        return int(sig.exit_code)
    except CLIError as exc:
        logger.error("CLI error (%s): %s", type(exc).__name__, exc)
        if verbose:
            logger.debug("Exception details:\n%s", traceback.format_exc())
            print(f"[DEBUG] {type(exc).__name__}: {exc}")
        print_error(
            str(exc),
            command=exc.command or command_name,
            hint=exc.hint,
        )
        return int(exc.exit_code)
    except sqlite3.Error as exc:
        logger.error("Database error: %s", exc)
        if verbose:
            print(traceback.format_exc())
        print_error(f"Database error: {exc}", command=command_name)
        return EXIT_DATABASE_ERROR
    except (FileNotFoundError, PermissionError, IsADirectoryError, NotADirectoryError) as exc:
        logger.error("Filesystem error: %s", exc)
        if verbose:
            print(traceback.format_exc())
        print_error(f"File/path error: {exc}", command=command_name)
        return EXIT_FILE_ERROR
    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user.")
        print_warning("Operation cancelled by user.")
        return EXIT_GENERAL_ERROR
    except Exception as exc:
        logger.exception("Unhandled error during CLI execution: %s", exc)
        if verbose:
            print_error(
                f"An unexpected error occurred: {exc}",
                command=command_name,
            )
            print(traceback.format_exc())
        else:
            print_error(
                "An unexpected error occurred while processing the file.",
                hint="Re-run with '--verbose' (-v) for detailed diagnostic information.",
            )
        return EXIT_GENERAL_ERROR
    finally:
        if verbose:
            remove_log_listener(_verbose_console_listener)


# ==============================================================================
# Typer / Click Bridge for Backward Compatibility with CliRunner Tests
# ==============================================================================


class _ArgparseBridgeGroup(typer.core.TyperGroup):
    """Click/Typer group bridge that routes invocations through the argparse `main()` pipeline."""

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        **extra: Any,
    ) -> Any:
        argv = list(sys.argv[1:] if args is None else args)
        code = main(argv)
        if standalone_mode:
            raise SystemExit(code)
        return code


app = typer.Typer(
    cls=_ArgparseBridgeGroup,
    add_completion=False,
    no_args_is_help=False,
    help="TraceLens metadata analysis and privacy inspection toolkit.",
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def _typer_root_callback(ctx: typer.Context) -> None:
    """Root callback retained for Typer introspection."""
    return None


if __name__ == "__main__":
    sys.exit(main())
