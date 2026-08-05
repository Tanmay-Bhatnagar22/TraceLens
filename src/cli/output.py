from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


APP_TITLE = "TraceLens"
APP_TAGLINE = "Intelligent Metadata Analysis and Privacy Inspection Toolkit"


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
    styles = {
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "info": "bold cyan",
    }
    prefix = {"success": "[+] ", "warning": "[!] ", "error": "[x] ", "info": "[i] "}.get(kind, "")
    console.print(f"[{styles.get(kind, 'bold cyan')}]{prefix}{text}[/{styles.get(kind, 'bold cyan')}]")


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return "" if value is None else str(value)


def mapping_table(title: str, mapping: Mapping[str, Any]) -> Table:
    table = Table(title=title, box=box.ROUNDED, show_lines=False, header_style="bold bright_cyan")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white", overflow="fold")
    for key, value in mapping.items():
        table.add_row(str(key), _stringify(value))
    return table


def records_table(rows: Iterable[Mapping[str, Any]], *, title: str = "History") -> Table:
    table = Table(title=title, box=box.ROUNDED, show_lines=False, header_style="bold bright_cyan")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("File Name", style="white", overflow="fold")
    table.add_column("Type", style="magenta", no_wrap=True)
    table.add_column("Size", style="green", no_wrap=True)
    table.add_column("Extracted At", style="yellow", no_wrap=True)
    table.add_column("Path", style="white", overflow="fold")

    for row in rows:
        table.add_row(
            str(row.get("id", "")),
            str(row.get("file_name", "")),
            str(row.get("file_type", "")),
            str(row.get("file_size_formatted", "")),
            str(row.get("extracted_at", "")),
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
