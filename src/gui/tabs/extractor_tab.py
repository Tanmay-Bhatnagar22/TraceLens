"""Extractor tab module for TraceLens GUI.

Handles file selection, extraction triggering, progress display, and metadata rendering.
"""

from __future__ import annotations

import os
from datetime import datetime
from tkinter import (
    BOTH,
    BOTTOM,
    DISABLED,
    FLAT,
    LEFT,
    NORMAL,
    WORD,
    X,
    W,
    Canvas,
    DoubleVar,
    Frame,
    Label,
    StringVar,
    filedialog,
    messagebox,
    scrolledtext,
    ttk,
)
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.gui.gui import MetadataAnalyzerApp

# Try importing extractor module for metadata extraction
try:
    from src.core.extractor import extractor
except ImportError:  # pragma: no cover - optional dependency
    extractor = None

# Try importing risk analyzer module
try:
    from src.core.risk import risk_analyzer
except ImportError:  # pragma: no cover - optional dependency
    risk_analyzer = None

from src.config.logging_config import get_logger

logger = get_logger("gui.extractor")


class ExtractorTab:
    """Component managing the Extractor tab UI and file extraction workflow."""

    def __init__(self, parent_frame: Frame, app: MetadataAnalyzerApp) -> None:
        self.parent = parent_frame
        self.app = app
        self.build_ui()

    def build_ui(self) -> None:
        """Construct the Extractor tab UI widgets."""
        c1 = Canvas(self.parent, bg="#ffffff", highlightthickness=0, border=0)
        c1.pack(fill=BOTH, expand=1)

        # Control buttons frame
        controls_frame = Frame(c1, bg="#f8f9fa", height=60)
        controls_frame.pack(side=BOTTOM, fill=X, padx=0, pady=0)
        controls_frame.pack_propagate(False)

        # Configure button styling with modern colors
        style = ttk.Style()
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=10)
        style.map(
            "TButton",
            foreground=[("pressed", "#ffffff"), ("active", "#ffffff")],
            background=[("pressed", "#0052a3"), ("active", "#0066cc")],
        )

        ttk.Button(controls_frame, text="Choose File", command=self.choose_file).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(controls_frame, text="Extract", command=self.extract_metadata).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(controls_frame, text="Editor", command=self.app.open_editor_with_current_metadata).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(controls_frame, text="Risk Analyzer", command=self.app.open_risk_analyzer_with_scan).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(controls_frame, text="Generate Report", command=self.app.generate_report).pack(side=LEFT, padx=10, pady=10)

        # Progress bar for file operations
        self.app.progress_var = DoubleVar()
        self.app.progress_bar = ttk.Progressbar(
            controls_frame,
            variable=self.app.progress_var,
            maximum=100,
            mode="indeterminate",
            length=40,
        )
        self.app.progress_bar.pack(side=LEFT, fill=X, expand=True, padx=(12, 10), pady=10)

        # Status bar for messages
        self.app.status_var = StringVar()
        self.app.status_var.set("Ready")
        status_frame = Frame(c1, bg="#2c3e50", height=30)
        status_frame.pack(side=BOTTOM, fill=X)
        status_frame.pack_propagate(False)
        status_bar = Label(
            status_frame,
            textvariable=self.app.status_var,
            relief=FLAT,
            anchor=W,
            font=("Segoe UI", 9),
            background="#2c3e50",
            foreground="#ecf0f1",
            padx=10,
        )
        status_bar.pack(side=LEFT, fill=X, expand=True, pady=8)

        # Text widget for displaying metadata with scrollbar
        self.app.c1_text = scrolledtext.ScrolledText(
            c1,
            wrap=WORD,
            bg="#ffffff",
            font=("Segoe UI", 11),
            fg="#333333",
            bd=0,
            relief=FLAT,
            highlightthickness=0,
            pady=15,
            padx=15,
        )
        self.app.c1_text.pack(fill=BOTH, expand=True, padx=0, pady=(0, 0))
        self.app.c1_text.tag_configure("bold", font=("Segoe UI", 11, "bold"), foreground="#0066cc")
        self.app.c1_text.tag_configure("header", font=("Segoe UI", 13, "bold"), foreground="#1a1a1a")
        self.show_welcome_text()

    def show_welcome_text(self) -> None:
        """Display welcome message in the metadata text widget."""
        if not self.app.c1_text:
            return
        self.app.c1_text.config(state=NORMAL)
        self.app.c1_text.delete(1.0, "end")
        self.app.c1_text.insert(
            "end",
            "Welcome to TraceLens: Intelligent Metadata Analysis & Privacy Inspection Toolkit\n",
            "header",
        )
        self.app.c1_text.insert(
            "end",
            "\nThis tool allows you to extract & edit metadata from various file types including images, documents, and audio files.\n\n",
        )
        self.app.c1_text.insert("end", "Getting Started:\n", "bold")
        self.app.c1_text.insert(
            "end",
            "1. Click 'Choose File' to select a file\n2. Click 'Extract' to analyze its metadata\n3. Use 'Generate report' to export the results\n\n",
        )
        self.app.c1_text.insert("end", "For more information, refer to the Help section in the menu bar.", "bold")
        self.app.c1_text.config(state=DISABLED)

    def choose_file(self) -> None:
        """Open file dialog for user to select a file to analyze."""
        filetypes = (
            ("All Files", "*.*"),
            ("Images", "*.jpg *.jpeg *.png *.gif *.bmp"),
            ("Documents", "*.pdf *.docx *.txt *.xlsx"),
            ("Audio", "*.mp3 *.wav *.flac"),
            (
                "Code Files",
                "*.py *.js *.java *.cpp *.c *.html *.css *.php *.rb *.go *.rs *.ts *.jsx *.tsx *.xml *.json *.yaml *.yml",
            ),
        )
        selected_file = filedialog.askopenfilename(filetypes=filetypes)
        if selected_file:
            self.app.file_path = selected_file
            self.app.extracted_metadata = {}
            self.app.risk_analysis = None
            file_size = os.path.getsize(selected_file) if os.path.exists(selected_file) else 0
            logger.info("Selected file: '%s' (Size: %d bytes)", selected_file, file_size)
            if self.app.progress_bar:
                self.app.progress_bar.start()
                if self.app.root:
                    self.app.root.after(2000, lambda: self.app.progress_bar.stop() if self.app.progress_bar else None)
            self.app.set_status(f"File selected: {os.path.basename(selected_file)}")
            if self.app.c1_text:
                self.app.c1_text.config(state=NORMAL)
                self.app.c1_text.delete(1.0, "end")
                self.app.c1_text.insert("end", "File Information\n", "header")
                self.app.c1_text.insert("end", "\n")
                self.app.c1_text.insert("end", f"Filename:  {os.path.basename(selected_file)}\n", "bold")
                self.app.c1_text.insert("end", f"Path:  {selected_file}\n", "bold")
                self.app.c1_text.insert("end", "\nStatus:  Ready for extraction\n\n", "bold")
                self.app.c1_text.insert("end", "Click 'Extract' to analyze the file metadata.", "bold")
                self.app.c1_text.config(state=DISABLED)

    def extract_metadata(self) -> None:
        """Extract metadata from the selected file and display results."""
        if not self.app.file_path:
            messagebox.showwarning("No File Selected", "Please choose a file first.")
            return

        if not extractor:
            logger.error("Extractor module is unavailable")
            messagebox.showerror("Error", "Extractor module not available.")
            return

        try:
            logger.info("Starting metadata extraction for: '%s'", self.app.file_path)
            if self.app.progress_bar:
                self.app.progress_bar.start()

            self.app.set_status("Extracting metadata...")
            if self.app.root:
                self.app.root.update()

            self.app.extracted_metadata, db_row = extractor.extract_and_store(self.app.file_path)

            if risk_analyzer and isinstance(self.app.extracted_metadata, dict) and "Error" not in self.app.extracted_metadata:
                try:
                    self.app.risk_analysis = risk_analyzer.analyze_metadata(
                        self.app.extracted_metadata,
                        self.app.file_path,
                        fallback_timestamps=self.app._get_timeline_fallbacks(
                            extracted_at=datetime.now().isoformat(sep=" ", timespec="seconds")
                        ),
                    )
                    if self.app.risk_analysis:
                        score = self.app.risk_analysis.get("risk_score", 0)
                        level = self.app.risk_analysis.get("risk_level", "Unknown")
                        logger.info("Privacy risk evaluation for '%s': Score %s/100 (%s)", os.path.basename(self.app.file_path), score, level)
                except Exception as risk_err:
                    logger.warning("Privacy risk analysis warning: %s", risk_err)
                    self.app.risk_analysis = None
            else:
                self.app.risk_analysis = None

            if self.app.progress_bar:
                self.app.progress_bar.stop()

            self.display_extracted_metadata(self.app.extracted_metadata, self.app.file_path, db_row)
            self.app._render_risk_analysis(self.app.risk_analysis)

            if isinstance(self.app.extracted_metadata, dict) and "Error" not in self.app.extracted_metadata:
                num_fields = len(self.app.extracted_metadata)
                logger.info("Successfully extracted %d metadata fields from '%s'", num_fields, os.path.basename(self.app.file_path))
                self.app.set_status(f"Successfully extracted {num_fields} metadata fields")
            else:
                err_msg = self.app.extracted_metadata.get("Error") if isinstance(self.app.extracted_metadata, dict) else "Unknown"
                logger.warning("Extraction completed with notice for '%s': %s", os.path.basename(self.app.file_path), err_msg)
                self.app.set_status("Extraction completed")

            try:
                if callable(self.app.history_refresh):
                    self.app.history_refresh()
            except Exception:
                pass

        except Exception as e:
            if self.app.progress_bar:
                self.app.progress_bar.stop()
            logger.error("Extraction failed for '%s': %s", self.app.file_path, e)
            self.app.set_status(f"Extraction error: {str(e)}")
            messagebox.showerror("Extraction Error", f"Failed to extract metadata: {str(e)}")

    def display_extracted_metadata(self, metadata: Any, file_path: str, db_row: Any) -> None:
        """Display extracted metadata in the text widget."""
        if not self.app.c1_text:
            return

        self.app.c1_text.config(state=NORMAL)
        self.app.c1_text.delete(1.0, "end")
        self.app.c1_text.insert("end", "Extracted Metadata\n", "header")
        self.app.c1_text.insert("end", f"File: {os.path.basename(file_path)}\n\n", "bold")

        if isinstance(metadata, dict):
            if "Error" in metadata:
                self.app.c1_text.insert("end", f"Error: {metadata['Error']}\n", "bold")
            else:
                for key, value in metadata.items():
                    self.app.c1_text.insert("end", f"{key}: ", "bold")
                    self.app.c1_text.insert("end", f"{value}\n")
        else:
            self.app.c1_text.insert("end", str(metadata))

        if db_row:
            def _fmt(dt_str):
                if not dt_str:
                    return ""
                try:
                    return datetime.fromisoformat(dt_str).strftime("%b %d, %Y %I:%M %p")
                except Exception:
                    return dt_str

            extracted_at_disp = _fmt(db_row[5]) if len(db_row) > 5 else ""
            modified_on_disp = _fmt(db_row[6]) if len(db_row) > 6 else ""

            self.app.c1_text.insert("end", "\n")
            self.app.c1_text.insert("end", "Extracted At: ", "bold")
            self.app.c1_text.insert("end", f"{extracted_at_disp}\n")
            self.app.c1_text.insert("end", "Modified On: ", "bold")
            self.app.c1_text.insert("end", f"{modified_on_disp}\n")

        self.app.c1_text.config(state=DISABLED)
