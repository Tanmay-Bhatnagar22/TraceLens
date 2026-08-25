"""Batch Process and Folder Extraction dialog module for TraceLens application.

Provides a multi-threaded batch metadata extraction interface with:
- Single file and folder extraction (recursive / flat)
- File extension filtering and deduplication
- Modern Material-inspired metric cards
- Live progress bar and non-blocking asynchronous execution
- Privacy risk level evaluation and forensic timeline scoring
- Detail inspector and batch report exporting (CSV/JSON)
"""

from __future__ import annotations

import csv
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import (
    BOTH,
    BOTTOM,
    CENTER,
    DISABLED,
    END,
    FLAT,
    LEFT,
    NO,
    NORMAL,
    RIGHT,
    SOLID,
    TOP,
    W,
    X,
    Y,
    YES,
    BooleanVar,
    Button,
    Canvas,
    DoubleVar,
    Frame,
    Label,
    Menu,
    StringVar,
    Toplevel,
    filedialog,
    messagebox,
    scrolledtext,
    ttk,
)
from typing import TYPE_CHECKING, Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.logging_config import get_logger

logger = get_logger("gui.batch")

# Optional core dependencies
try:
    from src.core.extractor import extractor
except ImportError:  # pragma: no cover
    extractor = None

try:
    from src.core.risk import risk_analyzer
except ImportError:  # pragma: no cover
    risk_analyzer = None

try:
    from src.core.database import db
except ImportError:  # pragma: no cover
    db = None



def format_file_size(size_in_bytes: int | float) -> str:
    """Format byte size into human-readable string.

    Args:
        size_in_bytes: Numeric size in bytes.

    Returns:
        str: Formatted string such as '1.2 MB' or '450 KB'.
    """
    try:
        val = float(size_in_bytes)
    except (ValueError, TypeError):
        return "0 B"

    if val < 0:
        return "0 B"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if val < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(val)} B"
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} TB"


SUPPORTED_FILTER_PRESETS: dict[str, tuple[str, ...]] = {
    "All Supported Formats": (
        ".pdf",
        ".docx",
        ".doc",
        ".txt",
        ".csv",
        ".xlsx",
        ".xls",
        ".pptx",
        ".ppt",
        ".md",
        ".json",
        ".xml",
        ".html",
        ".htm",
        ".rtf",
        ".log",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".tiff",
        ".tif",
        ".ico",
        ".svg",
        ".mp3",
        ".wav",
        ".flac",
        ".aac",
        ".ogg",
        ".mp4",
        ".avi",
        ".mkv",
        ".mov",
        ".wmv",
        ".webm",
        ".py",
        ".c",
        ".cpp",
        ".java",
        ".js",
    ),
    "Documents (*.pdf, *.docx, *.txt, *.csv, *.xlsx)": (
        ".pdf",
        ".docx",
        ".doc",
        ".txt",
        ".csv",
        ".xlsx",
        ".xls",
        ".pptx",
        ".ppt",
        ".md",
        ".json",
        ".xml",
        ".rtf",
        ".log",
    ),
    "Images (*.jpg, *.png, *.gif, *.bmp, *.webp, *.tiff)": (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".tiff",
        ".tif",
        ".ico",
        ".svg",
    ),
    "Audio & Video (*.mp4, *.mp3, *.wav, *.avi, *.mkv)": (
        ".mp3",
        ".wav",
        ".flac",
        ".aac",
        ".ogg",
        ".mp4",
        ".avi",
        ".mkv",
        ".mov",
        ".wmv",
        ".webm",
    ),
    "Code & Scripts (*.py, *.js, *.html, *.css, *.json)": (
        ".py",
        ".js",
        ".html",
        ".htm",
        ".css",
        ".json",
        ".c",
        ".cpp",
        ".h",
        ".java",
        ".sh",
        ".bat",
        ".ps1",
    ),
    "All Files (*.*)": (),
}


class BatchProcessDialog:
    """Modern Batch Process and Folder Extraction Dialog for TraceLens.

    Features:
    - Add individual files or entire directory trees (recursive/flat).
    - File extension filter presets with automatic path deduplication.
    - Responsive Material-inspired metric summary cards.
    - Live progress bar with asynchronous non-blocking thread execution.
    - Dual Start/Stop extraction triggers (Toolbar and Bottom action bar).
    - Privacy risk scoring and automatic database storage.
    - Detailed metadata inspector and CSV/JSON export capabilities.
    """

    def __init__(self, parent: Any, app: Any = None) -> None:
        self.parent = parent
        self.app = app

        self.window: Toplevel | None = None
        self.file_items: list[dict[str, Any]] = []
        self.path_set: set[str] = set()

        # Thread execution control
        self.is_processing = False
        self.stop_requested = False
        self.worker_thread: threading.Thread | None = None

        # UI reactive variables
        self.recursive_var: BooleanVar | None = None
        self.filter_var: StringVar | None = None
        self.progress_var: DoubleVar | None = None
        self.status_var: StringVar | None = None

        # Metric card labels
        self.card_files_val: Label | None = None
        self.card_size_val: Label | None = None
        self.card_status_val: Label | None = None
        self.card_risk_val: Label | None = None

        # Treeview widget
        self.tree: ttk.Treeview | None = None
        self.progress_bar: ttk.Progressbar | None = None

        # Button references
        self.btn_add_files: ttk.Button | None = None
        self.btn_add_folder: ttk.Button | None = None
        self.btn_remove: ttk.Button | None = None
        self.btn_clear: ttk.Button | None = None
        self.btn_tb_start: ttk.Button | None = None
        self.btn_tb_stop: ttk.Button | None = None
        self.btn_start: ttk.Button | None = None
        self.btn_stop: ttk.Button | None = None
        self.btn_export: ttk.Button | None = None
        self.btn_details: ttk.Button | None = None

    def show(self) -> Toplevel:
        """Construct and display the dialog window."""
        self.window = Toplevel(self.parent) if self.parent else Toplevel()
        self.window.title("TraceLens - Batch Metadata Extraction & Folder Processing")
        self.window.configure(bg="#f5f7fa")

        # Dimensions & positioning
        min_width = 920
        min_height = 660
        self.window.minsize(780, 520)

        # Center on parent window
        try:
            self.parent.update_idletasks()
            px = self.parent.winfo_x()
            py = self.parent.winfo_y()
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            x = max(0, px + (pw - min_width) // 2)
            y = max(0, py + (ph - min_height) // 2)
            self.window.geometry(f"{min_width}x{min_height}+{x}+{y}")
        except Exception:
            self.window.geometry(f"{min_width}x{min_height}")

        self.window.transient(self.parent)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        # Initialize reactive vars
        self.recursive_var = BooleanVar(value=True)
        self.filter_var = StringVar(value="All Supported Formats")
        self.progress_var = DoubleVar(value=0.0)
        self.status_var = StringVar(value="Ready. Add files or folders, then click 'Start Extraction' to begin.")

        self._build_ui()
        self._update_metrics()

        try:
            self.window.grab_set()
        except Exception:
            pass

        return self.window

    def _build_ui(self) -> None:
        """Construct the UI layout components with guaranteed bottom visibility."""
        # 1. Header Banner (Packed TOP)
        header_frame = Frame(self.window, bg="#0066cc", height=65)
        header_frame.pack(fill=X, side=TOP)
        header_frame.pack_propagate(False)

        header_content = Frame(header_frame, bg="#0066cc")
        header_content.pack(fill=BOTH, expand=True, padx=18, pady=8)

        title_lbl = Label(
            header_content,
            text="Batch Process & Folder Extraction",
            font=("Segoe UI", 14, "bold"),
            bg="#0066cc",
            fg="#ffffff",
            anchor=W,
        )
        title_lbl.pack(anchor=W)

        subtitle_lbl = Label(
            header_content,
            text="Extract metadata, evaluate privacy risks, and store records across multiple files and directories",
            font=("Segoe UI", 9),
            bg="#0066cc",
            fg="#d0e5ff",
            anchor=W,
        )
        subtitle_lbl.pack(anchor=W, pady=(1, 0))

        # Main Container
        main_container = Frame(self.window, bg="#f5f7fa")
        main_container.pack(fill=BOTH, expand=True, padx=14, pady=10)

        # CRITICAL LAYOUT ORDER:
        # 1) Pack bottom action bar FIRST (side=BOTTOM) to guarantee it's always visible
        self._build_bottom_controls(main_container)

        # 2) Pack live progress section SECOND (side=BOTTOM) above the bottom bar
        self._build_progress_section(main_container)

        # 3) Pack metric overview cards THIRD (side=TOP)
        self._build_metric_cards(main_container)

        # 4) Pack toolbar FOURTH (side=TOP)
        self._build_toolbar(main_container)

        # 5) Pack table LAST with fill=BOTH, expand=True so it fills the remaining central area
        self._build_treeview(main_container)

    def _build_metric_cards(self, parent: Frame) -> None:
        """Create responsive material-inspired metric cards."""
        cards_frame = Frame(parent, bg="#f5f7fa")
        cards_frame.pack(side=TOP, fill=X, pady=(0, 8))

        # Configure 4 columns
        for col_idx in range(4):
            cards_frame.columnconfigure(col_idx, weight=1, uniform="metric_cards")

        # Card 1: Total Files
        self.card_files_val = self._create_card(
            cards_frame,
            title="TOTAL FILES",
            initial_value="0",
            subtitle="Queued for processing",
            col=0,
            header_bg="#3b82f6",
        )

        # Card 2: Total Size
        self.card_size_val = self._create_card(
            cards_frame,
            title="TOTAL SIZE",
            initial_value="0 B",
            subtitle="Estimated disk volume",
            col=1,
            header_bg="#6366f1",
        )

        # Card 3: Completion Progress
        self.card_status_val = self._create_card(
            cards_frame,
            title="COMPLETION",
            initial_value="0 / 0",
            subtitle="Processed successfully",
            col=2,
            header_bg="#10b981",
        )

        # Card 4: Risk Summary
        self.card_risk_val = self._create_card(
            cards_frame,
            title="RISK BREAKDOWN",
            initial_value="0 LOW | 0 MED | 0 HIGH",
            subtitle="Privacy sensitivity rating",
            col=3,
            header_bg="#f59e0b",
        )

    def _create_card(
        self,
        parent: Frame,
        title: str,
        initial_value: str,
        subtitle: str,
        col: int,
        header_bg: str = "#3b82f6",
    ) -> Label:
        """Helper to create a single card with border and clean styling."""
        outer_frame = Frame(parent, bg="#dcdfe6", highlightthickness=0, bd=1)
        outer_frame.grid(row=0, column=col, padx=4, sticky="nsew")

        inner_frame = Frame(outer_frame, bg="#ffffff")
        inner_frame.pack(fill=BOTH, expand=True, padx=1, pady=1)

        top_bar = Frame(inner_frame, bg=header_bg, height=3)
        top_bar.pack(fill=X, side=TOP)

        content = Frame(inner_frame, bg="#ffffff")
        content.pack(fill=BOTH, expand=True, padx=10, pady=7)

        title_lbl = Label(
            content,
            text=title,
            font=("Segoe UI", 8, "bold"),
            fg="#64748b",
            bg="#ffffff",
            anchor=W,
        )
        title_lbl.pack(anchor=W)

        val_lbl = Label(
            content,
            text=initial_value,
            font=("Segoe UI", 12, "bold"),
            fg="#1e293b",
            bg="#ffffff",
            anchor=W,
        )
        val_lbl.pack(anchor=W, pady=(2, 1))

        sub_lbl = Label(
            content,
            text=subtitle,
            font=("Segoe UI", 7),
            fg="#94a3b8",
            bg="#ffffff",
            anchor=W,
        )
        sub_lbl.pack(anchor=W)

        return val_lbl

    def _build_toolbar(self, parent: Frame) -> None:
        """Create toolbar with file/folder selection, filter, and prominent Start Extraction trigger."""
        toolbar_frame = Frame(parent, bg="#ffffff", bd=1, relief=SOLID)
        toolbar_frame.pack(side=TOP, fill=X, pady=(0, 8))

        inner_tb = Frame(toolbar_frame, bg="#ffffff")
        inner_tb.pack(fill=X, padx=10, pady=8)

        # Left side: File & Folder addition controls
        self.btn_add_files = ttk.Button(inner_tb, text="Add Files...", command=self.add_files)
        self.btn_add_files.pack(side=LEFT, padx=(0, 5))

        self.btn_add_folder = ttk.Button(inner_tb, text="Add Folder...", command=self.add_folder)
        self.btn_add_folder.pack(side=LEFT, padx=(0, 5))

        self.btn_remove = ttk.Button(inner_tb, text="Remove Selected", command=self.remove_selected)
        self.btn_remove.pack(side=LEFT, padx=(0, 5))

        self.btn_clear = ttk.Button(inner_tb, text="Clear List", command=self.clear_list)
        self.btn_clear.pack(side=LEFT, padx=(0, 12))

        # Middle: Options
        subfolder_chk = ttk.Checkbutton(
            inner_tb,
            text="Include Subfolders (Recursive)",
            variable=self.recursive_var,
        )
        subfolder_chk.pack(side=LEFT, padx=(0, 10))

        filter_lbl = Label(inner_tb, text="Filter:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#334155")
        filter_lbl.pack(side=LEFT, padx=(0, 4))

        filter_cb = ttk.Combobox(
            inner_tb,
            textvariable=self.filter_var,
            values=list(SUPPORTED_FILTER_PRESETS.keys()),
            state="readonly",
            width=22,
        )
        filter_cb.pack(side=LEFT, padx=(0, 10))

        # Right side: Prominent Quick-Action Start Extraction & Stop buttons
        self.btn_tb_start = ttk.Button(
            inner_tb,
            text="Start Extraction",
            command=self.start_processing,
        )
        self.btn_tb_start.pack(side=RIGHT, padx=(4, 0))

        self.btn_tb_stop = ttk.Button(
            inner_tb,
            text="Stop",
            command=self.stop_processing,
            state=DISABLED,
        )
        self.btn_tb_stop.pack(side=RIGHT, padx=(4, 0))

    def _build_treeview(self, parent: Frame) -> None:
        """Create Treeview table with scrollbars and custom column headers."""
        table_container = Frame(parent, bg="#ffffff", bd=1, relief=SOLID)
        table_container.pack(side=TOP, fill=BOTH, expand=True, pady=(0, 8))

        columns = ("idx", "status", "name", "ext", "size", "risk", "path")

        style = ttk.Style()
        style.configure(
            "Batch.Treeview",
            font=("Segoe UI", 9),
            rowheight=24,
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground="#1e293b",
        )
        style.configure(
            "Batch.Treeview.Heading",
            font=("Segoe UI", 9, "bold"),
            padding=(4, 4),
            background="#e2e8f0",
            foreground="#0f172a",
        )

        self.tree = ttk.Treeview(
            table_container,
            columns=columns,
            show="headings",
            style="Batch.Treeview",
            selectmode="extended",
        )

        # Configure columns
        self.tree.heading("idx", text="#", anchor="center")
        self.tree.heading("status", text="Status", anchor="center")
        self.tree.heading("name", text="File Name", anchor="w")
        self.tree.heading("ext", text="Type", anchor="center")
        self.tree.heading("size", text="Size", anchor="e")
        self.tree.heading("risk", text="Risk Level", anchor="center")
        self.tree.heading("path", text="File Path / Details", anchor="w")

        self.tree.column("idx", width=45, anchor="center", stretch=False)
        self.tree.column("status", width=95, anchor="center", stretch=False)
        self.tree.column("name", width=180, anchor="w", stretch=False)
        self.tree.column("ext", width=65, anchor="center", stretch=False)
        self.tree.column("size", width=80, anchor="e", stretch=False)
        self.tree.column("risk", width=95, anchor="center", stretch=False)
        self.tree.column("path", width=320, anchor="w", stretch=True)


        # Scrollbars
        vsb = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)

        # Configure item tags for clean status / risk styling
        self.tree.tag_configure("risk_high", foreground="#dc2626")
        self.tree.tag_configure("risk_medium", foreground="#d97706")
        self.tree.tag_configure("risk_low", foreground="#16a34a")
        self.tree.tag_configure("status_failed", foreground="#dc2626")
        self.tree.tag_configure("status_success", foreground="#16a34a")
        self.tree.tag_configure("status_processing", foreground="#0066cc")

        # Double click to view details
        self.tree.bind("<Double-1>", lambda e: self.view_selected_details())

    def _build_progress_section(self, parent: Frame) -> None:
        """Create progress bar and dynamic live status text."""
        prog_frame = Frame(parent, bg="#f5f7fa")
        prog_frame.pack(side=BOTTOM, fill=X, pady=(4, 6))

        self.progress_bar = ttk.Progressbar(
            prog_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        )
        self.progress_bar.pack(fill=X, pady=(0, 3))

        status_lbl = Label(
            prog_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            bg="#f5f7fa",
            fg="#475569",
            anchor=W,
        )
        status_lbl.pack(fill=X)

    def _build_bottom_controls(self, parent: Frame) -> None:
        """Create bottom action buttons."""
        bottom_frame = Frame(parent, bg="#f5f7fa")
        bottom_frame.pack(side=BOTTOM, fill=X, pady=(4, 0))

        # Left action buttons
        self.btn_details = ttk.Button(
            bottom_frame,
            text="View Details",
            command=self.view_selected_details,
        )
        self.btn_details.pack(side=LEFT, padx=(0, 6))

        self.btn_export = ttk.Button(
            bottom_frame,
            text="Export Results...",
            command=self.export_results,
        )
        self.btn_export.pack(side=LEFT, padx=(0, 6))

        # Right action buttons
        btn_close = ttk.Button(bottom_frame, text="Close", command=self._on_close)
        btn_close.pack(side=RIGHT, padx=(6, 0))

        self.btn_stop = ttk.Button(
            bottom_frame,
            text="Stop",
            command=self.stop_processing,
            state=DISABLED,
        )
        self.btn_stop.pack(side=RIGHT, padx=(6, 0))

        self.btn_start = ttk.Button(
            bottom_frame,
            text="Start Extraction",
            command=self.start_processing,
        )
        self.btn_start.pack(side=RIGHT, padx=(6, 0))

    # ------------------------------------------------------------------
    # File & Folder Selection Logic
    # ------------------------------------------------------------------
    def add_files(self) -> None:
        """Open file dialog to add individual files to the queue."""
        filetypes = (
            ("All Supported Files", "*.pdf;*.docx;*.doc;*.txt;*.csv;*.xlsx;*.jpg;*.jpeg;*.png;*.gif;*.bmp;*.mp4;*.mp3;*.py"),
            ("PDF Documents", "*.pdf"),
            ("Images", "*.jpg;*.jpeg;*.png;*.gif;*.bmp;*.webp;*.tiff"),
            ("Office & Text Documents", "*.docx;*.doc;*.txt;*.csv;*.xlsx;*.pptx;*.md;*.json"),
            ("Audio & Video", "*.mp3;*.wav;*.mp4;*.avi;*.mkv"),
            ("All Files", "*.*"),
        )
        selected_files = filedialog.askopenfilenames(
            title="Select Files for Metadata Extraction",
            parent=self.window,
            filetypes=filetypes,
        )
        if not selected_files:
            return

        added_count = self._ingest_paths(selected_files)
        self.status_var.set(
            f"Added {added_count} new file(s). Total queued: {len(self.file_items)} file(s). Click 'Start Extraction' to begin."
        )
        self._update_metrics()

    def add_folder(self) -> None:
        """Open folder dialog and scan files according to recursion and filter settings."""
        folder_path = filedialog.askdirectory(
            title="Select Folder for Metadata Extraction",
            parent=self.window,
        )
        if not folder_path:
            return

        is_recursive = self.recursive_var.get() if self.recursive_var else True
        chosen_filter = self.filter_var.get() if self.filter_var else "All Supported Formats"
        allowed_exts = SUPPORTED_FILTER_PRESETS.get(chosen_filter, ())

        discovered_paths: list[str] = []

        try:
            if is_recursive:
                for root_dir, _, files in os.walk(folder_path):
                    for filename in files:
                        ext = os.path.splitext(filename)[1].lower()
                        if not allowed_exts or ext in allowed_exts:
                            full_path = os.path.join(root_dir, filename)
                            discovered_paths.append(full_path)
            else:
                with os.scandir(folder_path) as entries:
                    for entry in entries:
                        if entry.is_file():
                            ext = os.path.splitext(entry.name)[1].lower()
                            if not allowed_exts or ext in allowed_exts:
                                discovered_paths.append(entry.path)
        except Exception as err:
            messagebox.showerror(
                "Scan Error",
                f"Failed to scan folder '{folder_path}':\n{err}",
                parent=self.window,
            )
            return

        if not discovered_paths:
            messagebox.showinfo(
                "No Matching Files",
                f"No files matching the filter '{chosen_filter}' were found in '{os.path.basename(folder_path)}'.",
                parent=self.window,
            )
            return

        added_count = self._ingest_paths(discovered_paths)
        folder_name = os.path.basename(folder_path) or folder_path
        mode_text = "recursively" if is_recursive else "flat"
        self.status_var.set(
            f"Scanned '{folder_name}' ({mode_text}): added {added_count} new file(s). Click 'Start Extraction' to begin."
        )
        self._update_metrics()

    def _ingest_paths(self, paths: list[str] | tuple[str, ...]) -> int:
        """Add new paths to internal list and Treeview, avoiding duplicates."""
        added = 0
        for path_str in paths:
            norm_path = os.path.abspath(path_str)
            if norm_path in self.path_set:
                continue

            try:
                stat = os.stat(norm_path)
                size_bytes = stat.st_size
            except Exception:
                size_bytes = 0

            filename = os.path.basename(norm_path)
            ext = os.path.splitext(filename)[1].upper().lstrip(".") or "FILE"

            item_dict: dict[str, Any] = {
                "path": norm_path,
                "name": filename,
                "ext": ext,
                "size_bytes": size_bytes,
                "size_formatted": format_file_size(size_bytes),
                "status": "Pending",
                "risk_level": "N/A",
                "risk_score": 0,
                "metadata": None,
                "error": None,
                "tree_id": None,
            }

            self.path_set.add(norm_path)
            self.file_items.append(item_dict)
            added += 1

            # Insert into Treeview
            if self.tree:
                idx = len(self.file_items)
                tree_id = self.tree.insert(
                    "",
                    END,
                    values=(
                        idx,
                        "Pending",
                        filename,
                        ext,
                        item_dict["size_formatted"],
                        "-",
                        norm_path,
                    ),
                )
                item_dict["tree_id"] = tree_id

        return added

    def remove_selected(self) -> None:
        """Remove selected items from the Treeview and queue."""
        if not self.tree or self.is_processing:
            return

        selected_ids = self.tree.selection()
        if not selected_ids:
            return

        id_set = set(selected_ids)
        new_items: list[dict[str, Any]] = []
        self.path_set.clear()

        for item in self.file_items:
            if item.get("tree_id") in id_set:
                continue
            new_items.append(item)
            self.path_set.add(item["path"])

        self.file_items = new_items

        # Re-render treeview to update indexing
        self._refresh_treeview_rows()
        self._update_metrics()
        self.status_var.set(f"Removed {len(id_set)} item(s). {len(self.file_items)} remaining.")

    def clear_list(self) -> None:
        """Clear all items from the queue and treeview."""
        if self.is_processing:
            return

        self.file_items.clear()
        self.path_set.clear()
        if self.tree:
            for child in self.tree.get_children():
                self.tree.delete(child)

        self.progress_var.set(0.0)
        self.status_var.set("List cleared. Ready to add files or folders.")
        self._update_metrics()

    def _refresh_treeview_rows(self) -> None:
        """Re-populate all Treeview rows from file_items."""
        if not self.tree:
            return

        for child in self.tree.get_children():
            self.tree.delete(child)

        for idx, item in enumerate(self.file_items, start=1):
            status_text = item.get("status", "Pending")
            risk_text = item.get("risk_level", "-")
            if risk_text == "N/A":
                risk_text = "-"

            tags = ()
            if status_text == "Failed":
                tags = ("status_failed",)
            elif status_text == "Success":
                if risk_text == "HIGH":
                    tags = ("risk_high",)
                elif risk_text == "MEDIUM":
                    tags = ("risk_medium",)
                elif risk_text == "LOW":
                    tags = ("risk_low",)
                else:
                    tags = ("status_success",)

            tree_id = self.tree.insert(
                "",
                END,
                values=(
                    idx,
                    status_text,
                    item["name"],
                    item["ext"],
                    item["size_formatted"],
                    risk_text,
                    item.get("error") or item["path"],
                ),
                tags=tags,
            )
            item["tree_id"] = tree_id

    def _update_metrics(self) -> None:
        """Update top metric card values from self.file_items."""
        total_files = len(self.file_items)
        total_bytes = sum(item.get("size_bytes", 0) for item in self.file_items)

        processed = sum(1 for item in self.file_items if item.get("status") in ("Success", "Failed"))
        success_count = sum(1 for item in self.file_items if item.get("status") == "Success")

        low_count = sum(1 for item in self.file_items if item.get("risk_level") == "LOW")
        med_count = sum(1 for item in self.file_items if item.get("risk_level") == "MEDIUM")
        high_count = sum(1 for item in self.file_items if item.get("risk_level") == "HIGH")

        if self.card_files_val:
            self.card_files_val.config(text=str(total_files))

        if self.card_size_val:
            self.card_size_val.config(text=format_file_size(total_bytes))

        if self.card_status_val:
            pct = int((processed / total_files * 100)) if total_files > 0 else 0
            self.card_status_val.config(text=f"{success_count} / {total_files} ({pct}%)")

        if self.card_risk_val:
            self.card_risk_val.config(
                text=f"{low_count} LOW | {med_count} MED | {high_count} HIGH"
            )

    # ------------------------------------------------------------------
    # Batch Processing Execution (Threaded & Non-blocking)
    # ------------------------------------------------------------------
    def start_processing(self) -> None:
        """Begin batch extraction in background thread."""
        if not self.file_items:
            messagebox.showwarning(
                "No Files",
                "Please add files or folders to process first.",
                parent=self.window,
            )
            return

        if self.is_processing:
            return

        self.is_processing = True
        self.stop_requested = False

        # Update button states across both toolbar and bottom bar
        for btn in (self.btn_start, self.btn_tb_start):
            if btn:
                btn.config(state=DISABLED)
        for btn in (self.btn_add_files, self.btn_add_folder, self.btn_remove, self.btn_clear):
            if btn:
                btn.config(state=DISABLED)
        for btn in (self.btn_stop, self.btn_tb_stop):
            if btn:
                btn.config(state=NORMAL)

        self.progress_var.set(0.0)
        self.status_var.set(f"Starting batch extraction on {len(self.file_items)} file(s)...")

        self.worker_thread = threading.Thread(target=self._run_batch_worker, daemon=True)
        self.worker_thread.start()

    def stop_processing(self) -> None:
        """Request cancellation of the active worker thread."""
        if self.is_processing:
            self.stop_requested = True
            self.status_var.set("Stopping batch processing... please wait.")
            for btn in (self.btn_stop, self.btn_tb_stop):
                if btn:
                    btn.config(state=DISABLED)

    def _run_batch_worker(self) -> None:
        """Background worker thread executing metadata extraction and risk analysis."""
        total = len(self.file_items)
        processed = 0
        success_count = 0
        failed_count = 0
        batch_entries: list[dict[str, Any]] = []

        start_time = time.time()

        for idx, item in enumerate(self.file_items):
            if self.stop_requested:
                break

            file_path = item["path"]
            filename = item["name"]

            # UI Update: Mark row as extracting
            progress_pct = (idx / total) * 100 if total else 0
            self._dispatch_ui_update(
                item=item,
                status="Extracting...",
                risk_level="-",
                detail=file_path,
                tags=("status_processing",),
                progress_pct=progress_pct,
                status_text=f"[{idx + 1}/{total}] Extracting: {filename}...",
            )

            # Perform extraction
            meta_dict = None
            error_msg = None
            try:
                if extractor:
                    meta_dict, _ = extractor.extract_and_store(file_path)
                else:
                    error_msg = "Extractor core module is unavailable."
            except Exception as exc:
                error_msg = str(exc)

            if isinstance(meta_dict, dict) and "Error" in meta_dict:
                error_msg = meta_dict["Error"]
                meta_dict = None

            if meta_dict and isinstance(meta_dict, dict):
                # Calculate risk
                risk_level = "LOW"
                risk_score = 0
                if risk_analyzer:
                    try:
                        risk_info = risk_analyzer.analyze_file(meta_dict, file_path=file_path)
                        risk_level = risk_info.get("risk_level", "LOW")
                        risk_score = risk_info.get("risk_score", 0)
                        item["risk_info"] = risk_info
                    except Exception:
                        risk_level = "LOW"
                        risk_score = 0

                item["status"] = "Success"
                item["metadata"] = meta_dict
                item["risk_level"] = risk_level
                item["risk_score"] = risk_score
                item["error"] = None
                success_count += 1

                batch_entries.append({"file_path": file_path, "metadata": meta_dict})

                tag = "status_success"
                if risk_level == "HIGH":
                    tag = "risk_high"
                elif risk_level == "MEDIUM":
                    tag = "risk_medium"
                elif risk_level == "LOW":
                    tag = "risk_low"

                self._dispatch_ui_update(
                    item=item,
                    status="Success",
                    risk_level=risk_level,
                    detail=file_path,
                    tags=(tag,),
                    progress_pct=((idx + 1) / total) * 100,
                    status_text=f"[{idx + 1}/{total}] Success: {filename} (Risk: {risk_level})",
                )
            else:
                item["status"] = "Failed"
                item["metadata"] = None
                item["risk_level"] = "N/A"
                item["risk_score"] = 0
                item["error"] = error_msg or "Extraction returned no metadata."
                failed_count += 1

                self._dispatch_ui_update(
                    item=item,
                    status="Failed",
                    risk_level="-",
                    detail=item["error"],
                    tags=("status_failed",),
                    progress_pct=((idx + 1) / total) * 100,
                    status_text=f"[{idx + 1}/{total}] Failed: {filename}",
                )

            processed += 1

        elapsed = max(0.1, time.time() - start_time)

        # Batch Risk Analysis Summary Aggregation
        risk_batch_summary = None
        if risk_analyzer and batch_entries:
            try:
                risk_batch_summary = risk_analyzer.analyze_batch(batch_entries)
            except Exception:
                risk_batch_summary = None

        # Dispatch completion to UI
        self._dispatch_completion(
            processed=processed,
            success=success_count,
            failed=failed_count,
            stopped=self.stop_requested,
            elapsed_sec=elapsed,
            risk_summary=risk_batch_summary,
        )

    def _dispatch_ui_update(
        self,
        item: dict[str, Any],
        status: str,
        risk_level: str,
        detail: str,
        tags: tuple[str, ...],
        progress_pct: float,
        status_text: str,
    ) -> None:
        """Schedule thread-safe UI update on the main Tkinter thread."""
        if not self.window:
            return

        def _apply():
            try:
                if self.tree and item.get("tree_id"):
                    # Update row values
                    cur_vals = list(self.tree.item(item["tree_id"], "values"))
                    if len(cur_vals) >= 7:
                        cur_vals[1] = status
                        cur_vals[5] = risk_level
                        cur_vals[6] = detail
                        self.tree.item(item["tree_id"], values=cur_vals, tags=tags)

                if self.progress_var:
                    self.progress_var.set(progress_pct)
                if self.status_var:
                    self.status_var.set(status_text)

                self._update_metrics()
            except Exception:
                pass

        try:
            self.window.after(0, _apply)
        except Exception:
            pass

    def _dispatch_completion(
        self,
        processed: int,
        success: int,
        failed: int,
        stopped: bool,
        elapsed_sec: float,
        risk_summary: dict[str, Any] | None,
    ) -> None:
        """Schedule UI completion handler on the main thread."""
        if not self.window:
            return

        def _finish():
            self.is_processing = False
            self.stop_requested = False

            # Restore button states across both toolbar and bottom bar
            for btn in (self.btn_start, self.btn_tb_start):
                if btn:
                    btn.config(state=NORMAL)
            for btn in (self.btn_add_files, self.btn_add_folder, self.btn_remove, self.btn_clear):
                if btn:
                    btn.config(state=NORMAL)
            for btn in (self.btn_stop, self.btn_tb_stop):
                if btn:
                    btn.config(state=DISABLED)

            if not stopped:
                if self.progress_var:
                    self.progress_var.set(100.0)

            self._update_metrics()

            # Refresh parent app risk & history
            if self.app:
                if risk_summary:
                    self.app.risk_batch_summary = risk_summary
                    try:
                        self.app._render_risk_analysis(self.app.risk_analysis)
                    except Exception:
                        pass
                if callable(getattr(self.app, "history_refresh", None)):
                    try:
                        self.app.history_refresh()
                    except Exception:
                        pass

            speed = f"{processed / elapsed_sec:.1f} files/sec" if elapsed_sec > 0 else ""
            if stopped:
                status_msg = f"Batch extraction stopped by user. Processed {processed} file(s) ({success} success, {failed} failed)."
            else:
                status_msg = f"Batch extraction complete: {success} succeeded, {failed} failed in {elapsed_sec:.1f}s ({speed})."

            if self.status_var:
                self.status_var.set(status_msg)

            # Show completion message
            risk_counts = risk_summary.get("risk_counts", {}) if risk_summary else {}
            summary_dialog_msg = (
                f"Batch Extraction Summary:\n\n"
                f"• Total Processed: {processed}\n"
                f"• Successful: {success}\n"
                f"• Failed: {failed}\n"
                f"• Duration: {elapsed_sec:.1f} seconds\n"
            )
            if risk_counts:
                summary_dialog_msg += (
                    f"\nPrivacy Risk Breakdown:\n"
                    f"• LOW Risk: {risk_counts.get('LOW', 0)}\n"
                    f"• MEDIUM Risk: {risk_counts.get('MEDIUM', 0)}\n"
                    f"• HIGH Risk: {risk_counts.get('HIGH', 0)}"
                )

            if not stopped:
                messagebox.showinfo("Batch Process Complete", summary_dialog_msg, parent=self.window)

        try:
            self.window.after(0, _finish)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Detailed Inspector & Export Capabilities
    # ------------------------------------------------------------------
    def view_selected_details(self) -> None:
        """Open detailed metadata inspector popup for selected Treeview item."""
        if not self.tree:
            return

        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Select Item", "Please select a file from the list to view details.", parent=self.window)
            return

        selected_id = selection[0]
        matching_item = None
        for item in self.file_items:
            if item.get("tree_id") == selected_id:
                matching_item = item
                break

        if not matching_item:
            return

        # Build Inspector Window
        detail_win = Toplevel(self.window)
        detail_win.title(f"Metadata Details - {matching_item['name']}")
        detail_win.geometry("640x520")
        detail_win.configure(bg="#f5f7fa")
        detail_win.transient(self.window)

        header = Frame(detail_win, bg="#0066cc", height=50)
        header.pack(fill=X)
        header.pack_propagate(False)

        Label(
            header,
            text=f"Metadata: {matching_item['name']}",
            font=("Segoe UI", 12, "bold"),
            bg="#0066cc",
            fg="#ffffff",
        ).pack(side=LEFT, padx=15, pady=10)

        risk_lvl = matching_item.get("risk_level", "N/A")
        Label(
            header,
            text=f"Risk: {risk_lvl}",
            font=("Segoe UI", 10, "bold"),
            bg="#0066cc",
            fg="#ffd166" if risk_lvl == "MEDIUM" else ("#ff6b6b" if risk_lvl == "HIGH" else "#a7f3d0"),
        ).pack(side=RIGHT, padx=15, pady=10)

        body = Frame(detail_win, bg="#ffffff", bd=1, relief=SOLID)
        body.pack(fill=BOTH, expand=True, padx=12, pady=12)

        meta = matching_item.get("metadata")
        error = matching_item.get("error")

        text_area = scrolledtext.ScrolledText(body, wrap="word", font=("Consolas", 10), bg="#ffffff")
        text_area.pack(fill=BOTH, expand=True, padx=8, pady=8)

        text_area.insert(END, f"File Path : {matching_item['path']}\n")
        text_area.insert(END, f"File Size : {matching_item['size_formatted']}\n")
        text_area.insert(END, f"Status    : {matching_item['status']}\n")
        text_area.insert(END, f"Risk Level: {risk_lvl} (Score: {matching_item.get('risk_score', 0)}/100)\n")
        text_area.insert(END, "-" * 60 + "\n\n")

        if error:
            text_area.insert(END, f"Error Details:\n{error}\n")
        elif meta and isinstance(meta, dict):
            text_area.insert(END, "Extracted Key-Value Metadata:\n\n")
            for k, v in meta.items():
                text_area.insert(END, f"{k:<25}: {v}\n")

            risk_info = matching_item.get("risk_info")
            if risk_info and isinstance(risk_info, dict):
                reasons = risk_info.get("reasons", [])
                if reasons:
                    text_area.insert(END, "\n" + "-" * 60 + "\n")
                    text_area.insert(END, "Privacy Risk Analysis Observations:\n")
                    for r in reasons:
                        text_area.insert(END, f"• {r}\n")
        else:
            text_area.insert(END, "Metadata has not been extracted yet for this file.")

        text_area.config(state=DISABLED)

        btn_bar = Frame(detail_win, bg="#f5f7fa")
        btn_bar.pack(fill=X, padx=12, pady=(0, 12))
        ttk.Button(btn_bar, text="Close", command=detail_win.destroy).pack(side=RIGHT)

    def export_results(self) -> None:
        """Export batch metadata results to CSV or JSON."""
        if not self.file_items:
            messagebox.showinfo("No Data", "No items to export.", parent=self.window)
            return

        file_path = filedialog.asksaveasfilename(
            title="Export Batch Extraction Results",
            parent=self.window,
            defaultextension=".csv",
            filetypes=[("CSV File", "*.csv"), ("JSON File", "*.json"), ("All Files", "*.*")],
            initialfile=f"batch_metadata_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not file_path:
            return

        try:
            if file_path.lower().endswith(".json"):
                export_data = []
                for item in self.file_items:
                    export_data.append({
                        "file_name": item["name"],
                        "file_path": item["path"],
                        "file_size": item["size_formatted"],
                        "status": item["status"],
                        "risk_level": item["risk_level"],
                        "risk_score": item.get("risk_score", 0),
                        "metadata": item.get("metadata"),
                        "error": item.get("error"),
                    })
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=2)
            else:
                # Export as CSV
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "Index",
                        "File Name",
                        "File Type",
                        "File Size",
                        "Status",
                        "Risk Level",
                        "Risk Score",
                        "File Path",
                        "Metadata JSON / Error",
                    ])
                    for idx, item in enumerate(self.file_items, start=1):
                        meta_str = json.dumps(item.get("metadata")) if item.get("metadata") else (item.get("error") or "")
                        writer.writerow([
                            idx,
                            item["name"],
                            item["ext"],
                            item["size_formatted"],
                            item["status"],
                            item["risk_level"],
                            item.get("risk_score", 0),
                            item["path"],
                            meta_str,
                        ])

            messagebox.showinfo(
                "Export Successful",
                f"Batch results successfully exported to:\n{file_path}",
                parent=self.window,
            )
        except Exception as exc:
            messagebox.showerror(
                "Export Error",
                f"Failed to export batch results:\n{exc}",
                parent=self.window,
            )

    # ------------------------------------------------------------------
    # Window Close Handler
    # ------------------------------------------------------------------
    def _on_close(self) -> None:
        """Handle dialog close request with confirmation if extraction is active."""
        if self.is_processing:
            if not messagebox.askyesno(
                "Process in Progress",
                "Batch extraction is currently running. Do you want to cancel and exit?",
                parent=self.window,
            ):
                return
            self.stop_requested = True

        if self.window:
            self.window.destroy()
            self.window = None


def open_batch_process_dialog(parent: Any, app: Any = None) -> BatchProcessDialog:
    """Convenience function to instantiate and show the BatchProcessDialog."""
    logger.info("Opening Batch Process & Folder Extraction dialog")
    dialog = BatchProcessDialog(parent, app)
    dialog.show()
    return dialog
