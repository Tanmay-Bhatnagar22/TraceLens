"""Command-line interface for TraceLens.

Run this file directly from CMD/PowerShell:
    python cli.py

This CLI provides a menu-driven workflow similar to a terminal dashboard.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import db
import extractor
import report
import risk_analyzer
from main import main as run_gui_main


class Ansi:
    RESET = "\033[0m"
    CYAN = "\033[36m"
    BRIGHT_CYAN = "\033[96m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    GRAY = "\033[90m"


def _enable_ansi_windows() -> None:
    """Enable ANSI escape processing on modern Windows consoles."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        # If ANSI cannot be enabled, output still works without color.
        pass


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def color(text: str, ansi_code: str) -> str:
    return f"{ansi_code}{text}{Ansi.RESET}"


def banner() -> None:
    print(color("+--------------------------------------------------------------+", Ansi.BRIGHT_CYAN))
    print(color("|                        TRACE LENS CLI                        |", Ansi.BRIGHT_CYAN))
    print(color("+--------------------------------------------------------------+", Ansi.BRIGHT_CYAN))
    print(color("| Intelligent Metadata Analysis and Privacy Inspection Toolkit |", Ansi.CYAN))
    print(color("| One Command | Zero Hassle | Full Control                     |", Ansi.CYAN))
    print(color("+--------------------------------------------------------------+", Ansi.BRIGHT_CYAN))
    print(f"{color(' Type', Ansi.GRAY)} {color('help', Ansi.GREEN)} to list commands")
    print()


def print_menu() -> None:
    print(color("TraceLens - Main Menu", Ansi.BRIGHT_CYAN))
    print("1. Quick Extract")
    print("2. Analyze Risk")
    print("3. Generate Report")
    print("4. Batch Scan Folder")
    print("5. View Recent History")
    print("6. Launch GUI")
    print("7. Help")
    print("0. Exit")


def _normalize_path(raw: str) -> str:
    cleaned = raw.strip().strip('"').strip("'")
    return str(Path(cleaned).expanduser())


def prompt_path(prompt_text: str) -> str:
    while True:
        raw = input(f"{prompt_text}: ").strip()
        if not raw:
            print(color("Path cannot be empty.", Ansi.YELLOW))
            continue
        path = _normalize_path(raw)
        return path


def pretty_print_metadata(metadata: dict[str, Any]) -> None:
    print(color("\nExtracted Metadata", Ansi.BRIGHT_CYAN))
    print(color("-" * 60, Ansi.GRAY))
    for key, value in metadata.items():
        if isinstance(value, (dict, list)):
            val = json.dumps(value, ensure_ascii=False)
        else:
            val = str(value)
        print(f"{key}: {val}")
    print(color("-" * 60, Ansi.GRAY))


def quick_extract() -> None:
    file_path = prompt_path("Enter file path")
    metadata, _ = extractor.extract_and_store(file_path)

    if not metadata or "Error" in metadata:
        msg = metadata.get("Error", "Extraction failed.") if isinstance(metadata, dict) else "Extraction failed."
        print(color(f"Error: {msg}", Ansi.RED))
        return

    print(color("Metadata extracted and saved to database.", Ansi.GREEN))
    pretty_print_metadata(metadata)


def analyze_single_file_risk() -> None:
    file_path = prompt_path("Enter file path")
    metadata = extractor.extract(file_path)

    if not metadata or "Error" in metadata:
        msg = metadata.get("Error", "Extraction failed.") if isinstance(metadata, dict) else "Extraction failed."
        print(color(f"Error: {msg}", Ansi.RED))
        return

    analysis = risk_analyzer.analyze_metadata(metadata, file_path)

    print(color("\nRisk Analysis", Ansi.BRIGHT_CYAN))
    print(color("-" * 60, Ansi.GRAY))
    print(f"File: {analysis.get('file_name', '')}")
    print(f"Risk Score: {analysis.get('risk_score', 0)}/100")
    print(f"Risk Level: {analysis.get('risk_level', 'N/A')}")

    reasons = analysis.get("reasons", []) or []
    print("Reasons:")
    for reason in reasons:
        print(f"- {reason}")

    timeline = analysis.get("timeline", []) or []
    if timeline:
        print("Timeline:")
        for event in timeline:
            print(f"- {event.get('event', 'Event')}: {event.get('timestamp', '')}")
    print(color("-" * 60, Ansi.GRAY))


def generate_report_cli() -> None:
    file_path = prompt_path("Enter file path")
    metadata = extractor.extract(file_path)

    if not metadata or "Error" in metadata:
        msg = metadata.get("Error", "Extraction failed.") if isinstance(metadata, dict) else "Extraction failed."
        print(color(f"Error: {msg}", Ansi.RED))
        return

    analysis = risk_analyzer.analyze_metadata(metadata, file_path)
    text = report.generate_report_text(metadata, file_path, risk_analysis=analysis)

    print(color("\nReport Preview", Ansi.BRIGHT_CYAN))
    print(color("-" * 60, Ansi.GRAY))
    print(text[:1400] + ("\n..." if len(text) > 1400 else ""))
    print(color("-" * 60, Ansi.GRAY))

    choice = input("Save report as (txt/pdf/both/none) [both]: ").strip().lower() or "both"

    base = Path(file_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_out = ROOT_DIR / f"{base.stem}_report_{timestamp}.txt"
    pdf_out = ROOT_DIR / f"{base.stem}_report_{timestamp}.pdf"

    if choice in {"txt", "both"}:
        txt_out.write_text(text, encoding="utf-8")
        print(color(f"TXT saved: {txt_out}", Ansi.GREEN))

    if choice in {"pdf", "both"}:
        report.create_pdf_report_from_text(text, str(pdf_out))
        print(color(f"PDF saved: {pdf_out}", Ansi.GREEN))

    if choice not in {"txt", "pdf", "both", "none"}:
        print(color("Unknown option. Nothing saved.", Ansi.YELLOW))


def _iter_files(folder: Path) -> list[Path]:
    files: list[Path] = []
    for path in folder.rglob("*"):
        if path.is_file():
            files.append(path)
    return files


def batch_scan_folder() -> None:
    folder_raw = prompt_path("Enter folder path")
    folder = Path(folder_raw)
    if not folder.exists() or not folder.is_dir():
        print(color("Error: Folder not found.", Ansi.RED))
        return

    files = _iter_files(folder)
    if not files:
        print(color("No files found in the selected folder.", Ansi.YELLOW))
        return

    print(color(f"Scanning {len(files)} file(s)...", Ansi.CYAN))

    entries: list[dict[str, Any]] = []
    failed = 0

    for index, file_path in enumerate(files, 1):
        metadata = extractor.extract(str(file_path))
        if not metadata or "Error" in metadata:
            failed += 1
        else:
            db.insert_metadata(str(file_path), metadata)
            entries.append({"file_path": str(file_path), "metadata": metadata})

        if index % 25 == 0 or index == len(files):
            print(f"Processed {index}/{len(files)}")

    summary = risk_analyzer.analyze_batch(entries) if entries else {
        "total_files": 0,
        "risk_counts": {"LOW": 0, "MEDIUM": 0, "HIGH": 0},
    }

    counts = summary.get("risk_counts", {})
    print(color("\nBatch Scan Summary", Ansi.BRIGHT_CYAN))
    print(color("-" * 60, Ansi.GRAY))
    print(f"Successful: {len(entries)}")
    print(f"Failed: {failed}")
    print(f"LOW: {counts.get('LOW', 0)}")
    print(f"MEDIUM: {counts.get('MEDIUM', 0)}")
    print(f"HIGH: {counts.get('HIGH', 0)}")
    print(color("-" * 60, Ansi.GRAY))


def view_recent_history() -> None:
    raw = input("How many records to show? [10]: ").strip()
    limit = 10
    if raw:
        try:
            limit = max(1, int(raw))
        except ValueError:
            print(color("Invalid number. Showing 10 records.", Ansi.YELLOW))

    rows = db.get_recent_records(limit=limit)
    if not rows:
        print(color("No history records found.", Ansi.YELLOW))
        return

    print(color("\nRecent History", Ansi.BRIGHT_CYAN))
    print(color("-" * 100, Ansi.GRAY))
    for row in rows:
        record_id, file_path, file_name, size_fmt, file_type, extracted_at, _modified, _meta = row
        print(f"[{record_id}] {file_name} | {file_type} | {size_fmt} | {extracted_at}")
        print(f"    {file_path}")
    print(color("-" * 100, Ansi.GRAY))


def launch_gui() -> None:
    print(color("Launching TraceLens GUI...", Ansi.CYAN))
    run_gui_main()


def help_text() -> None:
    print(color("\nCommands", Ansi.BRIGHT_CYAN))
    print(color("-" * 60, Ansi.GRAY))
    print("1 -> Extract metadata from one file and save to DB")
    print("2 -> Analyze risk for one file")
    print("3 -> Generate report (TXT/PDF)")
    print("4 -> Batch scan folder and analyze risk summary")
    print("5 -> Show recent extraction history")
    print("6 -> Open existing Tkinter GUI")
    print("0 -> Exit")
    print("help -> Show this command list")
    print(color("-" * 60, Ansi.GRAY))


def run_cli() -> None:
    _enable_ansi_windows()

    while True:
        clear_screen()
        banner()
        print_menu()

        choice = input("\nChoose an option (or type help): ").strip().lower()
        print()

        if choice in {"0", "exit", "quit"}:
            print(color("Goodbye.", Ansi.GREEN))
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
            print(color("Invalid option. Type help for valid commands.", Ansi.YELLOW))

        input("\nPress Enter to continue...")


if __name__ == "__main__":
    run_cli()
