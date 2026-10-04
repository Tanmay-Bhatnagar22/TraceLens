"""Consistent CLI output and formatting layer for TraceLens."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console(highlight=False)


APP_TITLE = "TraceLens"
APP_TAGLINE = "Intelligent Metadata Analysis & Privacy Inspection Toolkit"


def _supports_unicode() -> bool:
    """Return True if the active stdout stream supports Unicode symbols."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✓✗!→─".encode(encoding)
        return True
    except Exception:
        return False


def get_symbols() -> dict[str, str]:
    """Return consistent visual symbols with automatic ASCII fallback."""
    if _supports_unicode():
        return {
            "success": "✓",
            "error": "✗",
            "warning": "!",
            "info": "→",
            "rule": "─",
        }
    return {
        "success": "[+]",
        "error": "[x]",
        "warning": "[!]",
        "info": "->",
        "rule": "-",
    }


def _safe_write_line(text: str = "") -> None:
    """Write a line to stdout safely across Windows, Linux, and macOS."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_text)


def print_header(title: str = APP_TITLE, subtitle: str | None = None) -> None:
    """Print a concise, consistent CLI section header."""
    symbols = get_symbols()
    if title == APP_TITLE and subtitle is None:
        header_text = Text(f" \n {APP_TITLE}: {APP_TAGLINE}", style="bold bright_cyan")
        rule_line = symbols["rule"] * (len(header_text.plain) + 2)
        console.print(header_text, soft_wrap=True)
        console.print(Text(rule_line, style="bright_cyan"), soft_wrap=True)
    else:
        rule_line = symbols["rule"] * len(title)
        console.print(Text(title, style="bold bright_cyan"), soft_wrap=True)
        console.print(Text(rule_line, style="bright_cyan"), soft_wrap=True)
        if subtitle:
            console.print(Text(subtitle, style="bright_cyan"), soft_wrap=True)
    _safe_write_line("")


def print_success(text: str) -> None:
    """Print a standardized success message."""
    sym = get_symbols()["success"]
    _safe_write_line(f"{sym} {text}")


def print_error(text: str, *, command: str | None = None, hint: str | None = None) -> None:
    """Print a standardized error message with optional usage hint."""
    sym = get_symbols()["error"]
    _safe_write_line(f"{sym} {text}")
    resolved_hint = hint
    if not resolved_hint and command:
        resolved_hint = f"Use 'tracelens {command} --help' for usage information."
    if resolved_hint:
        _safe_write_line("")
        _safe_write_line(resolved_hint)


def print_warning(text: str) -> None:
    """Print a standardized warning message."""
    sym = get_symbols()["warning"]
    _safe_write_line(f"{sym} {text}")


def print_info(text: str) -> None:
    """Print a standardized informational message."""
    sym = get_symbols()["info"]
    _safe_write_line(f"{sym} {text}")


def print_summary(
    title: str,
    items: Mapping[str, Any] | Iterable[str],
    *,
    style: str = "green",
    show_panel: bool = True,
) -> None:
    """Print a concise operation summary."""
    lines = lines_from_values(items) if isinstance(items, Mapping) else list(items)
    if show_panel:
        console.print(summary_panel(title, lines, style=style))
    else:
        _safe_write_line(title)
        _safe_write_line("")
        for line in lines:
            _safe_write_line(line)


def app_header() -> Panel:
    title = Text(APP_TITLE, style="bold bright_cyan")
    tagline = Text(APP_TAGLINE, style="cyan")
    return Panel(
        Group(title, tagline),
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def summary_panel(title: str, lines: Iterable[str], *, style: str = "green") -> Panel:
    body = "\n".join(lines) if lines else "No additional details available."
    return Panel(body, title=title, border_style=style, box=box.ROUNDED, padding=(1, 2))


def message(text: str, *, kind: str = "info") -> None:
    if kind == "success":
        print_success(text)
    elif kind == "warning":
        print_warning(text)
    elif kind == "error":
        print_error(text)
    else:
        print_info(text)


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return "" if value is None else str(value)


def format_display_timestamp(value: Any) -> str:
    """Format an ISO or database timestamp into 'DD Mon YYYY, HH:MM AM/PM' for CLI display."""
    if value is None:
        return "N/A"
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y, %I:%M %p")

    text = str(value).strip()
    if not text:
        return "N/A"

    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%d %b %Y, %I:%M %p")
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%d %b %Y, %I:%M %p")
        except ValueError:
            continue

    return text


def mapping_table(title: str, mapping: Mapping[str, Any]) -> Table:
    table = Table(title=title, box=box.ROUNDED, show_lines=False, header_style="bold bright_cyan")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white", overflow="fold")
    for key, value in mapping.items():
        table.add_row(str(key), _stringify(value))
    return table


def records_table(rows: Iterable[Mapping[str, Any]], *, title: str = "History") -> Table:
    table = Table(title=title, box=box.ROUNDED, show_lines=False, header_style="bold bright_cyan")
    table.add_column("No.", style="cyan", no_wrap=True)
    table.add_column("File Name", style="white", overflow="fold")
    table.add_column("Type", style="magenta", no_wrap=True)
    table.add_column("Size", style="green", no_wrap=True)
    table.add_column("Extracted At", style="yellow", no_wrap=True)
    table.add_column("Path", style="white", overflow="fold")

    for index, row in enumerate(rows, start=1):
        table.add_row(
            str(index),
            str(row.get("file_name", "")),
            str(row.get("file_type", "")),
            str(row.get("file_size_formatted", "")),
            format_display_timestamp(row.get("extracted_at")),
            str(row.get("file_path", "")),
        )
    return table


def risk_table(analysis: Mapping[str, Any]) -> Table:
    table = Table(title="Risk Analysis", box=box.ROUNDED, show_lines=False, header_style="bold bright_cyan")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="white", overflow="fold")
    table.add_row("File", str(analysis.get("file_name", "")))
    table.add_row("Risk Score", f"{analysis.get('risk_score', 0)}/100")
    table.add_row("Risk Level", str(analysis.get("risk_level", "N/A")))
    table.add_row("Matched Rules", ", ".join(analysis.get("matched_rules", []) or []) or "None")
    table.add_row("Timeline Events", str(analysis.get("event_count", 0)))
    return table


def timeline_table(timeline: Iterable[Mapping[str, Any]]) -> Table:
    table = Table(title="Forensic Timeline", box=box.ROUNDED, show_lines=False, header_style="bold bright_cyan")
    table.add_column("Event", style="cyan", overflow="fold")
    table.add_column("Timestamp", style="white", overflow="fold")
    for item in timeline:
        table.add_row(str(item.get("event", "")), str(item.get("timestamp", "")))
    return table


def lines_from_values(values: Mapping[str, Any]) -> list[str]:
    return [f"{key}: {_stringify(value)}" for key, value in values.items()]


def file_summary(file_path: Path, *, action: str, extra: Mapping[str, Any] | None = None) -> Panel:
    lines = [f"Action: {action}", f"File: {file_path}"]
    if extra:
        lines.extend(lines_from_values(extra))
    return summary_panel("Summary", lines, style="green")
