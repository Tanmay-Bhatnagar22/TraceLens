"""TraceLens command-line interface.

This module exposes the production CLI entrypoint with first-class support for the
TraceLens service layer (ServiceContainer, ExtractionService, RiskAnalysisService,
MetadataEditorService, HistoryService, ReportService, AnalyticsService).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import pandas as pd
import typer
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeRemainingColumn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT_DIR = PROJECT_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cli.output import app_header, console, mapping_table, message, records_table, risk_table, summary_panel, timeline_table
from src.cli.validation import CLIValidationError, collect_files, normalize_path, parse_key_value_pairs, require_directory, require_file
from src.config.logging_config import clear_logs, get_log_file_path, get_logger, get_recent_logs, setup_logging
from src.core.database import db as db_core
from src.core.editor import editor as editor_core
from src.core.extractor import extractor as extractor_core
from src.core.reports import report as report_core
from src.core.risk import risk_analyzer as risk_core
from src.core.services import (
    AnalyticsService,
    ExtractionService,
    HistoryService,
    MetadataEditorService,
    ReportService,
    RiskAnalysisService,
    ServiceContainer,
    get_service_container,
    set_service_container,
)
from src.models import (
    AnalyticsSummary,
    BatchExtractionResult,
    BatchRiskResult,
    ExtractionResult,
    MetadataRecord,
    ReportConfig,
    ReportResult,
    RiskAssessment,
)

logger = get_logger("cli")

# Backward compatibility references for tests and legacy callers
db = db_core
editor = editor_core
extractor = extractor_core
report = report_core
risk_analyzer = risk_core

APP_VERSION = "2.0.0"

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


app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="TraceLens metadata analysis and privacy inspection toolkit.",
    rich_markup_mode="rich",
)
history_app = typer.Typer(add_completion=False, help="Browse, inspect, and manage metadata history.")
config_app = typer.Typer(add_completion=False, help="Inspect and optimize TraceLens configuration.")
app.add_typer(history_app, name="history")
app.add_typer(config_app, name="config")


_active_state: CLIState = CLIState()


def _get_state() -> CLIState:
    global _active_state
    try:
        ctx = click.get_current_context()
    except RuntimeError:
        return _active_state

    cur: click.Context | None = ctx
    while cur is not None:
        if isinstance(cur.obj, CLIState):
            return cur.obj
        cur = cur.parent

    return _active_state


def get_services(state: CLIState | None = None) -> ServiceContainer:
    """Retrieve the active ServiceContainer, either from state, singleton, or dynamically configured."""
    if state is not None and state.container is not None:
        return state.container

    current_state = _get_state()
    if current_state.container is not None:
        return current_state.container

    # Respect custom components if monkeypatched or explicitly configured
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
    state = _get_state()
    state.container = container


def _set_state_from_context(
    ctx: typer.Context,
    verbose: bool,
    quiet: bool,
    db_path: str | None = None,
) -> CLIState:
    global _active_state
    state = CLIState(verbose=verbose, quiet=quiet, db_path=db_path)
    if db_path:
        state.container = ServiceContainer(db_path=db_path)
    ctx.obj = state
    _active_state = state
    # Initialize logging level according to verbosity flags
    level = "DEBUG" if verbose else ("WARNING" if quiet else "INFO")
    setup_logging(level=level, log_to_console=verbose)
    return state


def _emit_header(state: CLIState) -> None:
    if not state.quiet:
        console.print(app_header())


def _print_error(text: str) -> None:
    logger.error(text)
    message(f"Error: {text}", kind="error")


def _print_warning(text: str) -> None:
    logger.warning(text)
    message(text, kind="warning")


def _print_success(text: str) -> None:
    logger.info(text)
    message(text, kind="success")


def _normalize_path(raw: str) -> str:
    return str(normalize_path(raw))


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def banner() -> None:
    console.print(app_header())


def print_menu() -> None:
    console.print(
        summary_panel(
            "Available Commands",
            [
                "tracelens extract file.pdf",
                "tracelens analyze file.pdf",
                "tracelens sanitize file.pdf",
                "tracelens edit file.pdf --set Author=New Name",
                "tracelens report 12",
                "tracelens history",
                "tracelens analytics",
                "tracelens export json --output history.json",
                "tracelens config",
            ],
            style="bright_cyan",
        )
    )


def _enable_ansi_windows() -> None:
    return None


def prompt_path(prompt_text: str) -> str:
    while True:
        raw = input(f"{prompt_text}: ").strip()
        if not raw:
            _print_warning("Path cannot be empty.")
            continue
        return _normalize_path(raw)


def pretty_print_metadata(metadata: dict[str, Any]) -> None:
    console.print(mapping_table("Extracted Metadata", metadata))


def _row_to_record(row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(DB_COLUMNS, row, strict=False))


def _loads_metadata_blob(blob: Any) -> dict[str, Any]:
    if isinstance(blob, dict):
        return blob
    if not blob:
        return {}
    try:
        loaded = json.loads(blob)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _load_record(record_id: int) -> dict[str, Any] | None:
    services = get_services()
    record = services.history.get_record_by_id(record_id)
    if not record:
        return None
    return record.to_dict()


def _load_latest_record_for_path(file_path: str) -> dict[str, Any] | None:
    services = get_services()
    record = services.history.get_latest_by_path(file_path)
    if not record:
        return None
    return record.to_dict()


def _extract_metadata(file_path: str, *, save_to_db: bool = True) -> tuple[dict[str, Any], tuple[Any, ...] | None]:
    services = get_services()
    result = services.extraction.extract_file(file_path, persist=save_to_db)
    db_row = (result.db_record_id,) if result.db_record_id else None
    if not result.success and not result.metadata:
        return {"Error": result.error or "Extraction failed."}, db_row
    return result.metadata, db_row


def _resolve_input_files(targets: list[str]) -> list[Path]:
    return collect_files(targets, recursive=True)


def _summarize_history_rows(rows: list[dict[str, Any]], *, title: str = "History") -> None:
    if not rows:
        _print_warning("No history records found.")
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


def _write_export_file(dataframe: pd.DataFrame, output_path: Path, format_name: str) -> None:
    if format_name == "json":
        dataframe.to_json(output_path, orient="records", indent=2)
        return
    if format_name == "csv":
        dataframe.to_csv(output_path, index=False)
        return
    if format_name == "excel":
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            dataframe.to_excel(writer, sheet_name="Metadata", index=False)
        return
    if format_name == "xml":
        import xml.etree.ElementTree as ET

        root = ET.Element("metadata_records")
        for _, row in dataframe.iterrows():
            record = ET.SubElement(root, "record")
            for column in dataframe.columns:
                element = ET.SubElement(record, column.lower().replace(" ", "_"))
                value = row[column]
                element.text = "" if pd.isna(value) else str(value)
        ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)
        return
    if format_name == "pdf":
        services = get_services()
        services.report.reporter.create_pdf_from_dataframe(dataframe, str(output_path))
        return
    raise CLIValidationError(f"Unsupported export format: {format_name}")


def _choose_source_metadata(source: str) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    services = get_services()
    source_path = Path(source)
    if source_path.exists() and source_path.is_file():
        res = services.extraction.extract_file(str(source_path), persist=False)
        if not res.success or not isinstance(res.metadata, dict) or "Error" in res.metadata:
            raise CLIValidationError(res.error or "Extraction failed.")
        return str(source_path), res.metadata, None

    if source_path.exists() and source_path.is_dir():
        raise CLIValidationError("Report source must be a file or database record id.")

    try:
        record_id = int(source)
    except ValueError as exc:
        raise CLIValidationError(f"Source is not a valid file path or record id: {source}") from exc

    record = _load_record(record_id)
    if not record:
        raise CLIValidationError(f"No history record found for id {record_id}")

    return record["file_path"], record["full_metadata"], record


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show extra diagnostics."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Reduce output to essentials."),
    db_path: str | None = typer.Option(None, "--db-path", help="Custom SQLite database path to use."),
) -> None:
    state = _set_state_from_context(ctx, verbose=verbose, quiet=quiet, db_path=db_path)
    _emit_header(state)

    if ctx.invoked_subcommand is None:
        console.print(
            summary_panel(
                "Quick Start",
                [
                    "tracelens extract file.pdf",
                    "tracelens analyze file.pdf",
                    "tracelens sanitize file.pdf",
                    "tracelens report 12",
                    "tracelens history",
                    "tracelens analytics",
                    "tracelens export json --output history.json",
                ],
                style="bright_cyan",
            )
        )


@app.command()
def extract(
    targets: list[str] = typer.Argument(..., help="One or more files or folders to extract."),
    no_save: bool = typer.Option(False, "--no-save", help="Extract without storing results in the database."),
    recursive: bool = typer.Option(True, "--recursive/--flat", help="Scan folders recursively."),
) -> None:
    state = _get_state()
    services = get_services(state)
    logger.info("Extract command invoked for targets: %s (save_to_db=%s, recursive=%s)", targets, not no_save, recursive)
    try:
        files = collect_files(targets, recursive=recursive)
    except CLIValidationError as error:
        _print_error(str(error))
        raise typer.Exit(code=1) from error

    if not files:
        _print_warning("No files were found in the provided target(s).")
        raise typer.Exit(code=1)

    logger.debug("Found %d file(s) to extract", len(files))

    if len(files) == 1:
        file_path = files[0]
        with console.status(f"Extracting metadata from {file_path.name}...", spinner="dots"):
            result = services.extraction.extract_file(str(file_path), persist=not no_save)

        if not result.success:
            _print_error(result.error or "Extraction failed.")
            raise typer.Exit(code=1)

        logger.info("Successfully extracted metadata for %s", file_path)
        console.print(mapping_table(f"Metadata for {file_path.name}", result.metadata))
        summary_lines = [
            f"File: {file_path}",
            f"Saved to database: {'no' if no_save else 'yes'}",
        ]
        if result.db_record_id:
            summary_lines.append(f"Record ID: {result.db_record_id}")
        console.print(summary_panel("Extraction Complete", summary_lines, style="green"))
        return

    entries: list[dict[str, Any]] = []
    failed = 0
    progress_columns = [
        SpinnerColumn(style="cyan"),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    ]

    with Progress(*progress_columns, console=console) as progress:
        task = progress.add_task("Scanning files", total=len(files))
        for file_path in files:
            result = services.extraction.extract_file(str(file_path), persist=not no_save)
            if not result.success:
                failed += 1
                logger.warning("Failed extraction on batch file: %s (%s)", file_path, result.error)
            else:
                entries.append({"file_path": str(file_path), "metadata": result.metadata})
                logger.debug("Extracted metadata for: %s", file_path)
                if state.verbose:
                    console.print(f"[cyan]Processed[/cyan] {file_path}")
            progress.advance(task)

    logger.info("Batch extraction completed: %d successful, %d failed", len(entries), failed)
    batch_risk = services.risk.analyze_batch(entries) if entries else None
    low_cnt = batch_risk.low_risk_count if batch_risk else 0
    med_cnt = batch_risk.medium_risk_count if batch_risk else 0
    high_cnt = batch_risk.high_risk_count if batch_risk else 0

    console.print(
        summary_panel(
            "Batch Extraction Summary",
            [
                f"Successful: {len(entries)}",
                f"Failed: {failed}",
                f"LOW: {low_cnt}",
                f"MEDIUM: {med_cnt}",
                f"HIGH: {high_cnt}",
            ],
            style="green",
        )
    )
    if state.verbose and batch_risk and batch_risk.assessments:
        highest = max(batch_risk.assessments, key=lambda a: a.risk_score, default=None)
        if highest:
            console.print(summary_panel("Highest Risk Item", [json.dumps(highest.to_dict(), indent=2, default=str)], style="yellow"))


@app.command()
def analyze(
    targets: list[str] = typer.Argument(..., help="One or more files or folders to analyze."),
    recursive: bool = typer.Option(True, "--recursive/--flat", help="Scan folders recursively."),
) -> None:
    state = _get_state()
    services = get_services(state)
    logger.info("Analyze command invoked for targets: %s (recursive=%s)", targets, recursive)
    try:
        files = collect_files(targets, recursive=recursive)
    except CLIValidationError as error:
        _print_error(str(error))
        raise typer.Exit(code=1) from error

    if not files:
        _print_warning("No files were found in the provided target(s).")
        raise typer.Exit(code=1)

    analyses: list[RiskAssessment] = []
    failed_items: list[tuple[str, str]] = []
    progress_columns = [
        SpinnerColumn(style="cyan"),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    ]

    with Progress(*progress_columns, console=console) as progress:
        task = progress.add_task("Analyzing files", total=len(files))
        for file_path in files:
            ext_res = services.extraction.extract_file(str(file_path), persist=False)
            if not ext_res.success:
                failed_items.append((file_path.name, ext_res.error or "Extraction failed."))
            else:
                assessment = services.risk.analyze_metadata(ext_res.metadata, str(file_path))
                analyses.append(assessment)
            progress.advance(task)

    if len(files) == 1:
        if failed_items:
            _print_error(failed_items[0][1])
            raise typer.Exit(code=1)
        analysis = analyses[0]
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
        return

    summary_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "ERROR": len(failed_items)}
    for item in analyses:
        summary_counts[item.risk_level] = summary_counts.get(item.risk_level, 0) + 1

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
            style="green",
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


@app.command()
def sanitize(
    targets: list[str] = typer.Argument(..., help="One or more files or folders to sanitize."),
    backup: bool = typer.Option(True, "--backup/--no-backup", help="Create a .bak backup file before sanitizing."),
    recursive: bool = typer.Option(True, "--recursive/--flat", help="Scan folders recursively."),
) -> None:
    """Sanitize files by stripping sensitive metadata tags (GPS, camera, author, editing traces)."""
    state = _get_state()
    services = get_services(state)
    logger.info("Sanitize command invoked for targets: %s (backup=%s, recursive=%s)", targets, backup, recursive)
    try:
        files = collect_files(targets, recursive=recursive)
    except CLIValidationError as error:
        _print_error(str(error))
        raise typer.Exit(code=1) from error

    if not files:
        _print_warning("No files were found in the provided target(s).")
        raise typer.Exit(code=1)

    sanitized = 0
    failed = 0
    results: list[str] = []

    progress_columns = [
        SpinnerColumn(style="cyan"),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    ]

    with Progress(*progress_columns, console=console) as progress:
        task = progress.add_task("Sanitizing files", total=len(files))
        for file_path in files:
            success, msg = services.sanitize_file(str(file_path), backup=backup)
            if success:
                sanitized += 1
                results.append(f"Sanitized: {file_path.name}")
            else:
                failed += 1
                results.append(f"Failed: {file_path.name} - {msg}")
            progress.advance(task)

    console.print(
        summary_panel(
            "Sanitization Summary",
            [
                f"Total targets: {len(files)}",
                f"Successfully sanitized: {sanitized}",
                f"Failed/Unsupported: {failed}",
                f"Backup enabled: {'yes' if backup else 'no'}",
            ] + (results[:10] if not state.quiet else []),
            style="green" if failed == 0 else "yellow",
        )
    )
    if sanitized == 0 and failed > 0:
        raise typer.Exit(code=1)


@app.command()
def edit(
    file_path: str = typer.Argument(..., help="File whose metadata should be updated."),
    set_values: list[str] = typer.Option([], "--set", "-s", help="Metadata field updates in KEY=VALUE form."),
    metadata_file: str | None = typer.Option(None, "--metadata-file", help="JSON file containing metadata values to merge."),
    write_file: bool = typer.Option(True, help="Write changes back to the source file when supported."),
    save_db: bool = typer.Option(True, help="Save changes to the metadata database."),
) -> None:
    services = get_services()
    try:
        source = require_file(file_path)
    except CLIValidationError as error:
        _print_error(str(error))
        raise typer.Exit(code=1) from error

    updates: dict[str, Any] = {}
    if set_values:
        try:
            updates.update(parse_key_value_pairs(set_values))
        except CLIValidationError as error:
            _print_error(str(error))
            raise typer.Exit(code=1) from error

    if metadata_file:
        try:
            payload_path = require_file(metadata_file)
            loaded = json.loads(payload_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise CLIValidationError("Metadata file must contain a JSON object.")
            updates.update(loaded)
        except (OSError, json.JSONDecodeError, CLIValidationError) as error:
            _print_error(str(error))
            raise typer.Exit(code=1) from error

    if not updates:
        _print_warning("No metadata changes were supplied.")
        raise typer.Exit(code=1)

    ext_res = services.extraction.extract_file(str(source), persist=False)
    if ext_res.success and ext_res.metadata:
        base_metadata = ext_res.metadata
    else:
        latest_record = services.history.get_latest_by_path(str(source))
        if latest_record and latest_record.full_metadata:
            base_metadata = latest_record.full_metadata
        else:
            _print_error(ext_res.error or "Extraction failed.")
            raise typer.Exit(code=1)

    editable_text = services.editor.get_editable_text((str(source), base_metadata))
    parsed = services.editor.parse_editor_text(editable_text)
    parsed["metadata"].update(updates)

    is_valid, val_msg = services.editor.validate_metadata(parsed)
    if not is_valid:
        _print_error(f"Metadata validation error: {val_msg}")
        raise typer.Exit(code=1)

    db_result = (False, "Database update disabled")
    file_result = (False, "File write disabled")

    logger.info("Editing metadata for source: %s (updates=%s, save_db=%s, write_file=%s)", source, updates, save_db, write_file)
    if save_db:
        db_result = services.editor.save_to_database(str(source), parsed)
    if write_file:
        file_result = services.editor.write_to_file(str(source), parsed, backup=True)

    logger.info("Edit result - Database: %s, File: %s", db_result, file_result)
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
        raise typer.Exit(code=1)


@app.command(name="report")
def report_command(
    source: str = typer.Argument(..., help="File path or history record ID."),
    format_name: str = typer.Option("both", "--format", "-f", case_sensitive=False, help="Output format: txt, pdf, or both."),
    output_dir: str = typer.Option(str(PROJECT_ROOT), "--output-dir", help="Directory where reports should be written."),
) -> None:
    services = get_services()
    logger.info("Report command invoked for source: %s (format=%s, output_dir=%s)", source, format_name, output_dir)
    try:
        file_path_text, metadata, record = _choose_source_metadata(source)
    except CLIValidationError as error:
        _print_error(str(error))
        raise typer.Exit(code=1) from error

    output_directory = Path(output_dir).expanduser()
    output_directory.mkdir(parents=True, exist_ok=True)

    analysis = services.risk.analyze_metadata(metadata, file_path_text)
    text_report = services.report.generate_text_report(metadata, file_path_text, risk_analysis=analysis.to_dict())
    base_name = Path(file_path_text).stem or "tracelens_report"
    timestamp = _default_timestamp()
    outputs: list[Path] = []

    if format_name.lower() in {"txt", "both"}:
        txt_path = output_directory / f"{base_name}_report_{timestamp}.txt"
        txt_path.write_text(text_report, encoding="utf-8")
        outputs.append(txt_path)
        logger.debug("Generated text report: %s", txt_path)

    if format_name.lower() in {"pdf", "both"}:
        pdf_path = output_directory / f"{base_name}_report_{timestamp}.pdf"
        success, message = services.report.generate_pdf_report(
            metadata, file_path_text, str(pdf_path), risk_analysis=analysis.to_dict()
        )
        if success:
            outputs.append(pdf_path)
            logger.debug("Generated PDF report: %s", pdf_path)
        else:
            logger.error("Failed to generate PDF report: %s", message)
            _print_error(f"Failed to generate PDF report: {message}")

    logger.info("Reports generated successfully: %s", [str(p) for p in outputs])
    preview_lines = [_preview_report_text(text_report)]
    if record:
        preview_lines.insert(0, f"Record ID: {record.get('id')}")
    preview_lines.insert(0, f"Source: {file_path_text}")
    console.print(summary_panel("Report Preview", preview_lines, style="bright_cyan"))
    console.print(summary_panel("Saved Reports", [str(path) for path in outputs], style="green"))


@app.command()
def export(
    format_name: str = typer.Argument(..., help="Export format: json, xml, csv, excel, or pdf."),
    output: str | None = typer.Option(None, "--output", "-o", help="Destination file path."),
    query: str = typer.Option("", "--query", help="Text search across file name and file path."),
    file_type: str = typer.Option("All", "--file-type", help="Filter by file type."),
    date_filter: str = typer.Option("All Time", "--date-filter", help="Filter by time period."),
    sort: str = typer.Option("Date (Newest)", "--sort", help="Sort order for the export set."),
    limit: int = typer.Option(0, "--limit", min=0, help="Maximum records to export. 0 means no limit."),
) -> None:
    services = get_services()
    logger.info("Export command invoked (format=%s, output=%s, limit=%s)", format_name, output, limit)
    try:
        rows = _history_rows(limit=limit or 0, query=query, file_type=file_type, date_filter=date_filter, sort=sort)
    except Exception as error:
        _print_error(str(error))
        raise typer.Exit(code=1) from error

    if not rows:
        _print_warning("No records matched the selected export filters.")
        raise typer.Exit(code=1)

    dataframe = pd.DataFrame(rows, columns=[
        "ID",
        "File Path",
        "File Name",
        "File Size",
        "File Type",
        "Extracted At",
        "Modified On",
        "Full Metadata",
    ])

    format_normalized = format_name.lower()
    default_suffix = {
        "json": ".json",
        "xml": ".xml",
        "csv": ".csv",
        "excel": ".xlsx",
        "pdf": ".pdf",
    }.get(format_normalized)
    if not default_suffix:
        _print_error(f"Unsupported export format: {format_name}")
        raise typer.Exit(code=1)

    if output:
        output_path = Path(output).expanduser()
    else:
        output_path = PROJECT_ROOT / f"metadata_export_{_default_timestamp()}{default_suffix}"

    if output_path.suffix.lower() != default_suffix:
        output_path = output_path.with_suffix(default_suffix)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if format_normalized in {"json", "xml", "csv", "excel"}:
            services.report.export_records_dataframe(dataframe, format_normalized, str(output_path))
        else:
            _write_export_file(dataframe, output_path, format_normalized)
        logger.info("Export completed successfully: %d records exported to %s", len(dataframe), output_path)
    except Exception as error:
        logger.exception("Export failed for %s: %s", output_path, error)
        _print_error(str(error))
        raise typer.Exit(code=1) from error

    console.print(summary_panel("Export Complete", [f"Rows exported: {len(dataframe)}", f"Output: {output_path}"], style="green"))


@app.command(name="analytics")
def analytics_command(
    query: str = typer.Option("", "--query", help="Filter analytics by text search."),
    file_type: str = typer.Option("all", "--file-type", help="Filter by file type extension."),
    date_range: str = typer.Option("all", "--date-range", help="Date filter: all, today, week, month, year."),
) -> None:
    """Compute and display aggregate metadata analytics, privacy metrics, and dashboard intelligence."""
    services = get_services()
    summary = services.analytics.get_dashboard_metrics(date_range=date_range, file_type=file_type, search_query=query)

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
    console.print(summary_panel("Privacy Risk Breakdown", risk_lines, style="yellow" if summary.risk_distribution.get("HIGH", 0) > 0 else "green"))

    if summary.file_type_counts:
        type_lines = [f"{ftype}: {count}" for ftype, count in sorted(summary.file_type_counts.items(), key=lambda x: x[1], reverse=True)]
        console.print(summary_panel("File Type Distribution", type_lines, style="cyan"))

    if summary.top_threats:
        threat_lines = [f"- {t.get('reason', '')} ({t.get('count', 0)} occurrences)" for t in summary.top_threats]
        console.print(summary_panel("Top Discovered Threats", threat_lines, style="red"))


@app.command(name="stats")
def stats_command(
    query: str = typer.Option("", "--query", help="Filter analytics by text search."),
    file_type: str = typer.Option("all", "--file-type", help="Filter by file type extension."),
    date_range: str = typer.Option("all", "--date-range", help="Date filter: all, today, week, month, year."),
) -> None:
    """Display aggregate metadata analytics and metrics (alias for analytics)."""
    analytics_command(query=query, file_type=file_type, date_range=date_range)


@history_app.callback(invoke_without_command=True)
def history(
    ctx: typer.Context,
    limit: int = typer.Option(10, "--limit", min=1, help="Maximum number of records to display."),
    query: str = typer.Option("", "--query", help="Text search across file name and file path."),
    file_type: str = typer.Option("All", "--file-type", help="Filter by file type."),
    date_filter: str = typer.Option("All Time", "--date-filter", help="Filter by time period."),
    sort: str = typer.Option("Date (Newest)", "--sort", help="Sort order for displayed records."),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    rows = _history_rows(limit=limit, query=query, file_type=file_type, date_filter=date_filter, sort=sort)
    display_rows = [_row_to_record(row) for row in rows]
    _summarize_history_rows(display_rows, title="Recent History")


@history_app.command("delete")
def history_delete(record_id: int = typer.Argument(..., help="Database record ID to remove."), yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt.")) -> None:
    services = get_services()
    if not yes and not typer.confirm(f"Delete history record {record_id}?"):
        raise typer.Exit(code=1)
    if services.history.delete_record(record_id):
        console.print(summary_panel("History Updated", [f"Deleted record ID {record_id}"], style="green"))
        return
    _print_warning(f"Record {record_id} was not found.")
    raise typer.Exit(code=1)


@history_app.command("clear")
def history_clear(yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt.")) -> None:
    services = get_services()
    if not yes and not typer.confirm("Clear all metadata history?"):
        raise typer.Exit(code=1)
    if services.history.clear_history():
        console.print(summary_panel("History Cleared", ["All metadata records were removed from the database."], style="green"))
        return
    _print_error("Failed to clear metadata history.")
    raise typer.Exit(code=1)


@history_app.command("stats")
def history_stats() -> None:
    services = get_services()
    stats = services.history.get_database_stats()
    file_types = stats.get("file_types", {}) or {}
    console.print(
        summary_panel(
            "Database Statistics",
            [f"Total Records: {stats.get('total_records', 0)}"] + [f"{key or 'unknown'}: {value}" for key, value in file_types.items()],
            style="bright_cyan",
        )
    )


@config_app.callback(invoke_without_command=True)
def config(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    services = get_services()
    db_path = Path(services.database.db_path)
    log_file_path = get_log_file_path()
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


@app.command("logs")
def show_logs(
    lines: int = typer.Option(50, "--lines", "-n", help="Number of recent log lines to display."),
    clear: bool = typer.Option(False, "--clear", help="Clear log file and in-memory buffer."),
    path: bool = typer.Option(False, "--path", "-p", help="Print path to the active log file."),
) -> None:
    """Inspect recent application logs, view log path, or clear logs."""
    log_path = get_log_file_path()
    if path:
        console.print(str(log_path))
        return
    if clear:
        logger.info("Clearing logs via CLI command.")
        if clear_logs():
            console.print(summary_panel("Logs", ["Log buffer and file cleared."], style="green"))
        else:
            _print_error("Failed to clear log file.")
        return

    recent = get_recent_logs(max_entries=lines)
    if not recent:
        console.print(
            summary_panel(
                "TraceLens Logs",
                [f"Log file: {log_path}", "No log entries found in buffer or file."],
                style="yellow",
            )
        )
        return

    console.print(
        summary_panel(
            "TraceLens Logs",
            [f"Log file: {log_path}", f"Showing last {len(recent)} entries:"] + recent,
            style="bright_cyan",
        )
    )


@config_app.command("logs")
def config_logs(
    lines: int = typer.Option(50, "--lines", "-n", help="Number of recent log lines to display."),
    clear: bool = typer.Option(False, "--clear", help="Clear log file and in-memory buffer."),
    path: bool = typer.Option(False, "--path", "-p", help="Print path to the active log file."),
) -> None:
    """Inspect application logs from config submenu."""
    show_logs(lines=lines, clear=clear, path=path)


@config_app.command("optimize")
def config_optimize() -> None:
    services = get_services()
    res = services.history.optimize_database()
    if isinstance(res, tuple):
        success, msg = res
    else:
        success, msg = bool(res), "Optimization completed"
    if success:
        console.print(summary_panel("Configuration", [f"SQLite optimization completed: {msg}"], style="green"))
        return
    _print_error(f"Failed to optimize the database: {msg}")
    raise typer.Exit(code=1)


def _run_gui_main() -> None:
    from src.gui.gui import run_gui

    run_gui()


def _project_venv_python() -> Path:
    if os.name == "nt":
        return PROJECT_ROOT.parent / ".venv" / "Scripts" / "python.exe"
    return PROJECT_ROOT.parent / ".venv" / "bin" / "python"


@app.command()
def gui() -> None:
    console.print(summary_panel("Launching GUI", ["Starting the Tkinter application..."], style="cyan"))
    try:
        _run_gui_main()
    except ModuleNotFoundError as exc:
        missing = exc.name or "a required package"
        venv_python = _project_venv_python()

        if venv_python.exists() and venv_python.resolve() != Path(sys.executable).resolve():
            try:
                subprocess.Popen([str(venv_python), str(PROJECT_ROOT / "main.py")], cwd=str(PROJECT_ROOT.parent))
                console.print(summary_panel("GUI Launch", [f"Current Python is missing: {missing}", f"GUI launched using project venv: {venv_python}"], style="green"))
                return
            except Exception as launch_exc:
                _print_error(f"Could not launch with project venv: {launch_exc}")

        console.print(summary_panel("GUI Dependency Missing", [f"Missing package: {missing}", f"Current interpreter: {sys.executable}", "Install dependencies with: pip install -r requirements.txt"], style="yellow"))
    except Exception as exc:
        _print_error(f"Failed to launch GUI: {exc}")


def help_text() -> None:
    console.print(
        summary_panel(
            "Commands",
            [
                "extract    Extract metadata from files or folders",
                "analyze    Analyze privacy risk for files or folders",
                "sanitize   Strip sensitive metadata tags from files",
                "edit       Update metadata fields and save changes",
                "report     Generate TXT/PDF reports from a file or record",
                "history    Inspect and manage history records",
                "analytics  Show intelligent aggregate analytics & metrics",
                "export     Export filtered history to common formats",
                "config     Show or optimize runtime configuration",
                "gui        Launch the TraceLens desktop UI",
            ],
            style="bright_cyan",
        )
    )


def quick_extract() -> None:
    file_path = prompt_path("Enter file path")
    metadata, _ = extractor.extract_and_store(file_path)

    if not metadata or "Error" in metadata:
        msg = metadata.get("Error", "Extraction failed.") if isinstance(metadata, dict) else "Extraction failed."
        _print_error(msg)
        return

    _print_success("Metadata extracted and saved to database.")
    pretty_print_metadata(metadata)


def analyze_single_file_risk() -> None:
    file_path = prompt_path("Enter file path")
    metadata = extractor.extract(file_path)

    if not metadata or "Error" in metadata:
        msg = metadata.get("Error", "Extraction failed.") if isinstance(metadata, dict) else "Extraction failed."
        _print_error(msg)
        return

    analysis = risk_analyzer.analyze_metadata(metadata, file_path)
    console.print(risk_table(analysis))
    console.print(f"File: {analysis.get('file_name', '')}")
    console.print(f"Risk Score: {analysis.get('risk_score', 0)}/100")
    console.print(f"Risk Level: {analysis.get('risk_level', 'N/A')}")
    reasons = analysis.get("reasons", []) or []
    if reasons:
        console.print(summary_panel("Reasons", [f"- {reason}" for reason in reasons], style="yellow"))
    timeline = analysis.get("timeline", []) or []
    if timeline:
        console.print(timeline_table(timeline))
        for event in timeline:
            console.print(f"{event.get('event', 'Event')}: {event.get('timestamp', '')}")


def generate_report_cli() -> None:
    file_path = prompt_path("Enter file path")
    metadata = extractor.extract(file_path)

    if not metadata or "Error" in metadata:
        msg = metadata.get("Error", "Extraction failed.") if isinstance(metadata, dict) else "Extraction failed."
        _print_error(msg)
        return

    analysis = risk_analyzer.analyze_metadata(metadata, file_path)
    text = report.generate_report_text(metadata, file_path, risk_analysis=analysis)

    console.print(summary_panel("Report Preview", [_preview_report_text(text)], style="bright_cyan"))
    choice = input("Save report as (txt/pdf/both/none) [both]: ").strip().lower() or "both"

    base = Path(file_path)
    timestamp = _default_timestamp()
    txt_out = ROOT_DIR / f"{base.stem}_report_{timestamp}.txt"
    pdf_out = ROOT_DIR / f"{base.stem}_report_{timestamp}.pdf"

    if choice in {"txt", "both"}:
        txt_out.write_text(text, encoding="utf-8")
        _print_success(f"TXT saved: {txt_out}")

    if choice in {"pdf", "both"}:
        report.create_pdf_report_from_text(text, str(pdf_out))
        _print_success(f"PDF saved: {pdf_out}")

    if choice not in {"txt", "pdf", "both", "none"}:
        _print_warning("Unknown option. Nothing saved.")


def _iter_files(folder: Path) -> list[Path]:
    return [path for path in folder.rglob("*") if path.is_file()]


def batch_scan_folder() -> None:
    folder_raw = prompt_path("Enter folder path")
    try:
        folder = require_directory(folder_raw)
    except CLIValidationError as error:
        _print_error(str(error))
        return

    files = _iter_files(folder)
    if not files:
        _print_warning("No files found in the selected folder.")
        return

    console.print(summary_panel("Batch Scan", [f"Scanning {len(files)} file(s)..."], style="cyan"))
    entries: list[dict[str, Any]] = []
    failed = 0

    progress_columns = [
        SpinnerColumn(style="cyan"),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    ]
    with Progress(*progress_columns, console=console) as progress:
        task = progress.add_task("Processing files", total=len(files))
        for file_path in files:
            metadata = extractor.extract(str(file_path))
            if not metadata or "Error" in metadata:
                failed += 1
            else:
                db.insert_metadata(str(file_path), metadata)
                entries.append({"file_path": str(file_path), "metadata": metadata})
            progress.advance(task)

    summary = risk_analyzer.analyze_batch(entries) if entries else {"risk_counts": {"LOW": 0, "MEDIUM": 0, "HIGH": 0}}
    counts = summary.get("risk_counts", {})
    console.print(summary_panel("Batch Scan Summary", [f"Successful: {len(entries)}", f"Failed: {failed}", f"LOW: {counts.get('LOW', 0)}", f"MEDIUM: {counts.get('MEDIUM', 0)}", f"HIGH: {counts.get('HIGH', 0)}"], style="green"))


def view_recent_history() -> None:
    raw = input("How many records to show? [10]: ").strip()
    limit = 10
    if raw:
        try:
            limit = max(1, int(raw))
        except ValueError:
            _print_warning("Invalid number. Showing 10 records.")

    rows = db.get_recent_records(limit=limit)
    if not rows:
        _print_warning("No history records found.")
        return

    display_rows = [_row_to_record(row) for row in rows]
    _summarize_history_rows(display_rows, title="Recent History")


def launch_gui() -> None:
    console.print("Launching TraceLens GUI...")
    try:
        _run_gui_main()
    except ModuleNotFoundError as exc:
        missing = exc.name or "a required package"
        venv_python = _project_venv_python()

        if venv_python.exists() and venv_python.resolve() != Path(sys.executable).resolve():
            try:
                subprocess.Popen([str(venv_python), str(PROJECT_ROOT / "main.py")], cwd=str(PROJECT_ROOT.parent))
                console.print(f"Current Python is missing: {missing}")
                console.print(f"GUI launched using project venv: {venv_python}")
                return
            except Exception as launch_exc:
                console.print(f"Could not launch with project venv: {launch_exc}")

        console.print(f"GUI dependency missing: {missing}")
        console.print(f"Current interpreter: {sys.executable}")
        console.print("Install dependencies with: pip install -r requirements.txt")
    except Exception as exc:
        _print_error(f"Failed to launch GUI: {exc}")


def run_cli() -> None:
    _enable_ansi_windows()

    while True:
        clear_screen()
        banner()
        print_menu()

        choice = input("\nChoose an option (or type help): ").strip().lower()
        print()

        if choice in {"0", "exit", "quit"}:
            _print_success("Goodbye.")
            break

        if choice in {"7", "help"}:
            help_text()
        elif choice == "1":
            quick_extract()
        elif choice == "2":
            analyze_single_file_risk()
        elif choice == "3":
            generate_report_cli()
        elif choice == "4":
            batch_scan_folder()
        elif choice == "5":
            view_recent_history()
        elif choice == "6":
            launch_gui()
        else:
            _print_warning("Invalid option. Type help for valid commands.")

        input("\nPress Enter to continue...")


if __name__ == "__main__":
    app()
