"""GUI module for TraceLens application.

Provides Tkinter-based interface with tabs for file extraction, editing, and history management.
"""

from tkinter import *
from tkinter import Menu, filedialog
from tkinter import ttk
from tkinter import scrolledtext
from tkinter import messagebox
import os
import json
import tempfile
import db
import report
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import threading

# Try importing extractor module for metadata extraction
try:
    import extractor
except ImportError:  # pragma: no cover - optional dependency
    extractor = None

# Try importing editor module for metadata editing and writing
try:
    import editor
except ImportError:  # pragma: no cover - optional dependency
    editor = None

# Try importing risk analyzer module for privacy risk and timeline analysis
try:
    import risk_analyzer
except ImportError:  # pragma: no cover - optional dependency
    risk_analyzer = None


class MetadataAnalyzerApp:
    """Class-based GUI application for TraceLens.
    
    Provides Tkinter interface with tabs for:
    - Extractor: Extract metadata from files
    - Editor: Edit and manage extracted metadata
    - History: View and manage extraction history
    - Risk analyzer: Privacy risk scoring and forensic timeline visualization
    - Preview: Generate and view reports
    """

    NON_EDITABLE_FIELDS = {"File Name", "File Size", "File Type", "Extracted At", "Modified On"}

    def __init__(self) -> None:
        # Core state
        self.file_path = None
        self.extracted_metadata = {}

        # UI references
        self.root = None
        self.c1_text = None
        self.status_var = None
        self.progress_var = None
        self.progress_bar = None
        self.nb_widget = None
        self.tab2_ref = None
        self.tab5_ref = None
        self.tab4_ref = None
        self.editor_entry_fields = {}
        self.editor_entry_frame = None
        self.editor_canvas = None
        self.editor_status = None
        self.report_preview = None
        self.report_image_label = None
        self.report_preview_tk_img = None
        self.preview_image_zoom = 1.0  # Image zoom scale factor
        self.preview_base_image = None  # Store original PIL image
        self.preview_canvas = None  # Canvas for scrollable image
        self.preview_scrollbar = None  # Scrollbar for preview canvas
        self.risk_summary_text = None
        self.risk_chart_canvas = None
        self.timeline_chart_canvas = None
        self.risk_analysis = None
        self.risk_batch_summary = None

        # Layout info
        self.window_width = None
        self.window_height = None
        self.x_position = None
        self.y_position = None

        # Report state
        self.report_last_text = ""

        # Hooks
        self.history_refresh = None
        
        # Statistics cache
        self.stats_cache = None
        self.stats_cache_time = None
        self.stats_cache_duration = 30  # Cache for 30 seconds

    # ------------------------------------------------------------------
    # Application lifecycle
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Launch the GUI application.
        
        Initializes window, creates widgets, builds menu bar, and starts main event loop.
        """
        self._init_window()
        self._create_widgets()
        self._build_menu_bar()
        self._setup_keyboard_shortcuts()
        self.root.mainloop()

    # ------------------------------------------------------------------
    # Window and widgets
    # ------------------------------------------------------------------
    def _init_window(self) -> None:
        """Initialize main window with modern styling and centered positioning."""
        self.root = Tk()
        self.root.title("TraceLens: Intelligent Metadata Analysis & Privacy Inspection Toolkit")
        self.root.config(bg="#f5f7fa")

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.window_width = int(screen_width * 0.7)
        self.window_height = int(screen_height * 0.7)

        self.x_position = (screen_width - self.window_width) // 2
        self.y_position = (screen_height - self.window_height) // 2

        self.root.geometry(f"{self.window_width}x{self.window_height}+{self.x_position}+{self.y_position}")
        self.root.resizable(False, False)

        logo = PhotoImage(file="Metadata.png")
        self.root.iconphoto(True, logo)

    def _create_widgets(self) -> None:
        """Build UI components: title, notebook tabs (Extractor, Editor, History), controls, and status bar."""
        # Title label
        title_label = Label(self.root, text="TraceLens", bg="#f5f7fa", font=("Segoe UI", 24, "bold"), fg="#1a1a1a")
        title_label.place(x=10, y=10, width=self.window_width - 20, height=40)

        # Configure modern flat design theme
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#f5f7fa", borderwidth=0)
        style.configure("TNotebook.Tab", padding=[20, 10], font=("Segoe UI", 10))

        nb = ttk.Notebook(self.root)
        nb.place(x=10, y=55, width=self.window_width - 20, height=self.window_height - 70)
        self.nb_widget = nb

        tab1 = Frame(nb, bg="#ffffff")
        tab2 = Frame(nb, bg="#ffffff")
        tab3 = Frame(nb, bg="#ffffff")
        tab5 = Frame(nb, bg="#ffffff")
        tab4 = Frame(nb, bg="#ffffff")

        nb.add(tab1, text="Extractor")
        c1 = Canvas(tab1, bg="#ffffff", highlightthickness=0, border=0)
        c1.pack(fill=BOTH, expand=1)

        # Control buttons frame
        controls_frame = Frame(c1, bg="#f8f9fa", height=60)
        controls_frame.pack(side=BOTTOM, fill=X, padx=0, pady=0)
        controls_frame.pack_propagate(False)

        # Configure button styling with modern colors
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=10)
        style.map(
            "TButton",
            foreground=[("pressed", "#ffffff"), ("active", "#ffffff")],
            background=[("pressed", "#0052a3"), ("active", "#0066cc")],
        )

        ttk.Button(controls_frame, text="Choose File", command=self.choose_file).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(controls_frame, text="Extract", command=self.extract_metadata).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(controls_frame, text="Editor", command=self.open_editor_with_current_metadata).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(controls_frame, text="Risk Analyzer", command=self.open_risk_analyzer_with_scan).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(controls_frame, text="Generate Report", command=self.generate_report).pack(side=LEFT, padx=10, pady=10)

        # Progress bar for file operations
        self.progress_var = DoubleVar()
        self.progress_bar = ttk.Progressbar(controls_frame, variable=self.progress_var, maximum=100, mode="indeterminate", length=40)
        self.progress_bar.pack(side=LEFT, fill=X, expand=True, padx=(12, 10), pady=10)

        # Status bar for messages
        self.status_var = StringVar()
        self.status_var.set("Ready")
        status_frame = Frame(c1, bg="#2c3e50", height=30)
        status_frame.pack(side=BOTTOM, fill=X)
        status_frame.pack_propagate(False)
        status_bar = Label(status_frame, textvariable=self.status_var, relief=FLAT, anchor=W, font=("Segoe UI", 9), background="#2c3e50", foreground="#ecf0f1", padx=10)
        status_bar.pack(side=LEFT, fill=X, expand=True, pady=8)

        # Text widget for displaying metadata with scrollbar
        self.c1_text = scrolledtext.ScrolledText(c1, wrap=WORD, bg="#ffffff", font=("Segoe UI", 11), fg="#333333", bd=0, relief=FLAT, highlightthickness=0, pady=15, padx=15)
        self.c1_text.pack(fill=BOTH, expand=True, padx=0, pady=(0, 0))
        self.c1_text.tag_configure("bold", font=("Segoe UI", 11, "bold"), foreground="#0066cc")
        self.c1_text.tag_configure("header", font=("Segoe UI", 13, "bold"), foreground="#1a1a1a")
        self._show_welcome_text()

        # Editor tab setup
        nb.add(tab2, text="Editor")
        self.tab2_ref = tab2
        c2 = Frame(tab2, bg="#ffffff")
        c2.pack(fill=BOTH, expand=1)

        editor_controls = Frame(c2, bg="#f8f9fa", height=60)
        editor_controls.pack(side=BOTTOM, fill=X)
        editor_controls.pack_propagate(False)

        ttk.Button(editor_controls, text="Save Changes", command=self.save_editor_changes).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(editor_controls, text="Cancel", command=self.cancel_editor_changes).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(editor_controls, text="Add Metadata", command=self.add_metadata_field).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(editor_controls, text="Generate Report", command=self.generate_report).pack(side=LEFT, padx=10, pady=10)

        editor_status_frame = Frame(c2, bg="#2c3e50", height=30)
        editor_status_frame.pack(side=BOTTOM, fill=X)
        editor_status_frame.pack_propagate(False)
        self.editor_status = Label(editor_status_frame, text="", relief=FLAT, anchor=W, font=("Segoe UI", 9), background="#2c3e50", foreground="#ffffff", padx=10)
        self.editor_status.pack(side=LEFT, fill=X, expand=True, pady=8)

        editor_fields_container = Frame(c2, bg="#ffffff")
        editor_fields_container.pack(fill=BOTH, expand=True)

        Label(editor_fields_container, text="Metadata Editor", bg="#ffffff", font=("Segoe UI", 14, "bold"), fg="#1a1a1a", anchor=W).pack(fill=X, padx=15, pady=(12, 4))

        self.editor_canvas = Canvas(editor_fields_container, bg="#ffffff", highlightthickness=0, bd=0)
        self.editor_canvas.pack(side=LEFT, fill=BOTH, expand=True)

        self.editor_entry_frame = Frame(self.editor_canvas, bg="#ffffff")
        self.editor_canvas.create_window((0, 0), window=self.editor_entry_frame, anchor=NW)
        self.editor_entry_frame.bind("<Configure>", lambda e: self.editor_canvas.configure(scrollregion=self.editor_canvas.bbox("all")))

        def _on_mousewheel(event):
            delta_steps = 0
            if hasattr(event, "delta") and event.delta:
                delta_steps = int(-1 * (event.delta / 120))
            elif getattr(event, "num", None) == 4:
                delta_steps = -1
            elif getattr(event, "num", None) == 5:
                delta_steps = 1
            if delta_steps:
                self.editor_canvas.yview_scroll(delta_steps, "units")

        self.editor_canvas.bind("<MouseWheel>", _on_mousewheel)
        self.editor_canvas.bind("<Button-4>", _on_mousewheel)
        self.editor_canvas.bind("<Button-5>", _on_mousewheel)
        self.editor_entry_frame.bind("<MouseWheel>", _on_mousewheel)
        self.editor_entry_frame.bind("<Button-4>", _on_mousewheel)
        self.editor_entry_frame.bind("<Button-5>", _on_mousewheel)

        # History tab
        nb.add(tab3, text="History")

        # Risk analyzer tab
        nb.add(tab5, text="Risk analyzer")
        self.tab5_ref = tab5
        self._build_risk_tab(tab5)

        # Report tab: preview on the left, controls on the right
        nb.add(tab4, text="Preview")
        self.tab4_ref = tab4
        report_container = Frame(tab4, bg="#ffffff")
        report_container.pack(fill=BOTH, expand=True)

        preview_frame = Frame(report_container, bg="#e8e8e8")
        preview_frame.pack(side=LEFT, fill=BOTH, expand=True)
        preview_label = Label(preview_frame, text="Report Preview", bg="#e8e8e8", font=("Segoe UI", 12, "bold"), fg="#1a1a1a")
        preview_label.pack(anchor=W, padx=12, pady=(12, 6))

        self.report_preview = scrolledtext.ScrolledText(preview_frame, wrap=WORD, bg="#ffffff", font=("Segoe UI", 11), fg="#333333", bd=1, relief=SOLID, highlightthickness=0, pady=12, padx=12)
        self.report_preview.config(state=DISABLED)

        # Container for canvas and scrollbar
        image_container = Frame(preview_frame, bg="#e8e8e8")
        image_container.pack(fill=BOTH, expand=True, padx=12, pady=(0, 12))

        # Scrollbar for preview canvas
        self.preview_scrollbar = ttk.Scrollbar(image_container, orient="vertical")
        
        # Canvas for scrollable image preview
        self.preview_canvas = Canvas(image_container, bg="#e8e8e8", highlightthickness=0, bd=0)
        self.preview_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        
        self.preview_scrollbar.config(command=self.preview_canvas.yview)
        self.preview_canvas.config(yscrollcommand=self.preview_scrollbar.set)
        
        # Label inside canvas for image display
        self.report_image_label = Label(
            self.preview_canvas,
            bg="#e8e8e8",
            text="No report generated yet.\n\nGenerate a report from the Extractor or Editor tab to see preview.",
            font=("Segoe UI", 11),
            fg="#666666",
            justify=CENTER,
        )
        self.canvas_window_id = self.preview_canvas.create_window(0, 0, window=self.report_image_label, anchor="n")
        
        # Bind canvas configure event to center image when canvas size changes
        self.preview_canvas.bind('<Configure>', self._on_canvas_configure)
        
        # Bind mousewheel for scrolling
        def _on_preview_mousewheel(event):
            delta_steps = 0
            if hasattr(event, "delta") and event.delta:
                delta_steps = int(-1 * (event.delta / 120))
            elif getattr(event, "num", None) == 4:
                delta_steps = -1
            elif getattr(event, "num", None) == 5:
                delta_steps = 1
            if delta_steps:
                self.preview_canvas.yview_scroll(delta_steps, "units")

        self.preview_canvas.bind("<MouseWheel>", _on_preview_mousewheel)
        self.preview_canvas.bind("<Button-4>", _on_preview_mousewheel)
        self.preview_canvas.bind("<Button-5>", _on_preview_mousewheel)
        self.report_image_label.bind("<MouseWheel>", _on_preview_mousewheel)
        self.report_image_label.bind("<Button-4>", _on_preview_mousewheel)
        self.report_image_label.bind("<Button-5>", _on_preview_mousewheel)

        controls_side = Frame(report_container, bg="#f8f9fa", width=220)
        controls_side.pack(side=RIGHT, fill=Y, padx=2, pady=2)
        controls_side.pack_propagate(False)
        Label(controls_side, text="Actions", bg="#f8f9fa", font=("Segoe UI", 11, "bold"), fg="#1a1a1a").pack(anchor=W, padx=12, pady=(12, 6))
        Button(controls_side, text="Save Report", command=lambda: report.save_metadata(self.report_last_text), bg="#007acc", fg="white", font=("Segoe UI", 10, "bold"), relief=FLAT, cursor="hand2", pady=8).pack(fill=X, padx=12, pady=6)
        Button(controls_side, text="Print Report", command=lambda: report.print_metadata_report(self.report_last_text), bg="#28a745", fg="white", font=("Segoe UI", 10, "bold"), relief=FLAT, cursor="hand2", pady=8).pack(fill=X, padx=12, pady=6)
        
        Label(controls_side, text="Zoom", bg="#f8f9fa", font=("Segoe UI", 11, "bold"), fg="#1a1a1a").pack(anchor=W, padx=12, pady=(24, 6))
        zoom_frame = Frame(controls_side, bg="#f8f9fa")
        zoom_frame.pack(fill=X, padx=12, pady=6)
        Button(zoom_frame, text="+", command=self.zoom_in_image, bg="#007acc", fg="white", font=("Segoe UI", 10, "bold"), relief=FLAT, cursor="hand2", width=3).pack(side=LEFT, padx=(0, 6))
        Button(zoom_frame, text="−", command=self.zoom_out_image, bg="#007acc", fg="white", font=("Segoe UI", 10, "bold"), relief=FLAT, cursor="hand2", width=3).pack(side=LEFT, padx=(0, 6))
        Button(zoom_frame, text="Reset", command=self.reset_zoom_image, bg="#6c757d", fg="white", font=("Segoe UI", 9, "bold"), relief=FLAT, cursor="hand2", width=5).pack(side=LEFT)
        self.zoom_display_label = Label(controls_side, text="100%", bg="#f8f9fa", font=("Segoe UI", 10), fg="#333333")
        self.zoom_display_label.pack(anchor=W, padx=12, pady=(6, 0))

        # History tab widgets
        self._build_history_tab(tab3)

        nb.bind("<<NotebookTabChanged>>", lambda e: self._on_tab_changed(e, tab2, tab3, tab5))

    def _build_history_tab(self, tab3: Frame) -> None:
        """Construct history tab with search/filter/export controls.
        
        Creates search bar, filters, tree view for history, and action buttons.
        
        Args:
            tab3 (Frame): Tkinter Frame widget for the history tab.
        """
        history_container = Frame(tab3, bg="#ffffff")
        history_container.pack(fill=BOTH, expand=True, padx=10, pady=10)

        search_row1 = Frame(history_container, bg="#ffffff")
        search_row1.pack(fill=X, pady=(0, 12))

        Label(search_row1, text="Search:", bg="#ffffff", font=("Segoe UI", 10, "bold"), fg="#1a1a1a").pack(side=LEFT, padx=(0, 8))
        search_var = StringVar()
        search_entry = ttk.Entry(search_row1, textvariable=search_var, width=25, font=("Segoe UI", 10))
        search_entry.pack(side=LEFT, padx=(0, 15))

        Label(search_row1, text="File Type:", bg="#ffffff", font=("Segoe UI", 10, "bold"), fg="#1a1a1a").pack(side=LEFT, padx=(0, 8))
        filter_var = StringVar()
        filter_combo = ttk.Combobox(search_row1, textvariable=filter_var, width=16, state="readonly", font=("Segoe UI", 10))
        filter_combo["values"] = [
            "All",
            "pdf",
            "doc",
            "docx",
            "xlsx",
            "xls",
            "csv",
            "ppt",
            "pptx",
            "txt",
            "py",
            "json",
            "xml",
            "md",
            "log",
        ]
        filter_combo.set("All")
        filter_combo.pack(side=LEFT, padx=(0, 15))

        Label(search_row1, text="Date Range:", bg="#ffffff", font=("Segoe UI", 10, "bold"), fg="#1a1a1a").pack(side=LEFT, padx=(0, 8))
        date_var = StringVar()
        date_combo = ttk.Combobox(search_row1, textvariable=date_var, width=17, state="readonly", font=("Segoe UI", 10))
        date_combo["values"] = ["All Time", "Today", "This Week", "This Month", "Last 30 Days"]
        date_combo.set("All Time")
        date_combo.pack(side=LEFT, padx=(0, 15))

        Label(search_row1, text="Sort by:", bg="#ffffff", font=("Segoe UI", 10, "bold"), fg="#1a1a1a").pack(side=LEFT, padx=(0, 8))
        sort_var = StringVar()
        sort_combo = ttk.Combobox(search_row1, textvariable=sort_var, width=20, state="readonly", font=("Segoe UI", 10))
        sort_combo["values"] = [
            "Date (Newest)",
            "Date (Oldest)",
            "Name (A-Z)",
            "Name (Z-A)",
            "Size (Largest)",
            "Size (Smallest)",
        ]
        sort_combo.set("Date (Newest)")
        sort_combo.pack(side=LEFT, padx=(0, 15))

        tree_frame = Frame(history_container, bg="#ffffff")
        tree_frame.pack(fill=BOTH, expand=True)

        columns = ("S.No", "File Path", "File Name", "File Size", "File Type", "Extracted At", "Modified On", "Record ID")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings")

        for col in columns:
            tree.heading(col, text=col)
            if col == "S.No":
                tree.column(col, stretch=NO, minwidth=50, width=60, anchor=CENTER)
            elif col == "File Path":
                tree.column(col, stretch=YES, minwidth=220, width=260, anchor=W)
            elif col == "File Name":
                tree.column(col, stretch=YES, minwidth=160, width=190, anchor=W)
            elif col == "File Size":
                tree.column(col, stretch=NO, minwidth=90, width=110, anchor=CENTER)
            elif col == "File Type":
                tree.column(col, stretch=NO, minwidth=70, width=80, anchor=CENTER)
            elif col == "Extracted At":
                tree.column(col, stretch=NO, minwidth=150, width=180, anchor=CENTER)
            elif col == "Modified On":
                tree.column(col, stretch=NO, minwidth=150, width=180, anchor=CENTER)
            elif col == "Record ID":
                tree.column(col, stretch=NO, minwidth=0, width=0, anchor=CENTER)

        tree.pack(side=LEFT, fill=BOTH, expand=True)

        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        v_scrollbar.pack(side=RIGHT, fill=Y)
        tree.configure(yscrollcommand=v_scrollbar.set)

        h_scrollbar = ttk.Scrollbar(history_container, orient="horizontal", command=tree.xview)
        h_scrollbar.pack(side=BOTTOM, fill=X, pady=(4, 0))
        tree.configure(xscrollcommand=h_scrollbar.set)

        button_frame = Frame(history_container, bg="#ffffff")
        button_frame.pack(fill=X, pady=(12, 0))

        clear_btn = ttk.Button(button_frame, text="Clear Filters")
        clear_btn.pack(side=LEFT, padx=6)

        export_csv_btn = ttk.Button(button_frame, text="Export CSV")
        export_csv_btn.pack(side=LEFT, padx=6)
        export_excel_btn = ttk.Button(button_frame, text="Export Excel")
        export_excel_btn.pack(side=LEFT, padx=6)
        export_json_btn = ttk.Button(button_frame, text="Export JSON")
        export_json_btn.pack(side=LEFT, padx=6)
        export_xml_btn = ttk.Button(button_frame, text="Export XML")
        export_xml_btn.pack(side=LEFT, padx=6)
        export_pdf_btn = ttk.Button(button_frame, text="Export PDF")
        export_pdf_btn.pack(side=LEFT, padx=6)

        delete_btn = ttk.Button(button_frame, text="Delete")
        delete_btn.pack(side=RIGHT, padx=6)
        delete_all_btn = ttk.Button(button_frame, text="Delete All")
        delete_all_btn.pack(side=RIGHT, padx=6)
        refresh_btn = ttk.Button(button_frame, text="Refresh")
        refresh_btn.pack(side=RIGHT, padx=6)

        def humanize(dt_str: str) -> str:
            if not dt_str:
                return ""
            try:
                from datetime import datetime

                return datetime.fromisoformat(dt_str).strftime("%b %d, %Y %I:%M %p")
            except Exception:
                return dt_str

        def load_data():
            data = db.filter_and_search_data(search_var.get(), filter_var.get(), date_var.get(), sort_var.get())
            tree.delete(*tree.get_children())
            for idx, row in enumerate(data, start=1):
                extracted_at = humanize(row[5])
                modified_on = humanize(row[6])
                tree.insert("", END, values=(idx, row[1], row[2], row[3], row[4], extracted_at, modified_on, row[0]))
            return data

        def clear_filters():
            search_var.set("")
            filter_var.set("All")
            date_var.set("All Time")
            sort_var.set("Date (Newest)")
            search_entry.focus_set()
            load_data()

        def refresh_data():
            load_data()

        def delete_selected_record():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("No Selection", "Please select a record to delete.")
                return
            record_values = tree.item(selected[0])["values"]
            record_id = record_values[-1]
            if messagebox.askyesno("Confirm Delete", f"Delete record ID: {record_id}?"):
                if db.delete_record(record_id):
                    messagebox.showinfo("Success", "Record deleted successfully.")
                else:
                    messagebox.showerror("Error", "Failed to delete record.")
                load_data()

        def delete_all_records():
            if messagebox.askyesno("Confirm Delete", "Delete all metadata records? This cannot be undone."):
                if db.clear_metadata():
                    messagebox.showinfo("Success", "All records deleted.")
                else:
                    messagebox.showerror("Error", "Failed to delete records.")
                load_data()

        def export_handler(fmt):
            data = load_data()
            if not data:
                messagebox.showwarning("No Data", "No records to export with current filters.")
                return
            db.export_data(fmt, data)
            messagebox.showinfo("Export", f"Exported data as {fmt.upper()}.")

        search_var.trace("w", lambda *args: load_data())
        filter_var.trace("w", lambda *args: load_data())
        date_var.trace("w", lambda *args: load_data())
        sort_var.trace("w", lambda *args: load_data())

        clear_btn.config(command=clear_filters)
        refresh_btn.config(command=refresh_data)
        delete_btn.config(command=delete_selected_record)
        delete_all_btn.config(command=delete_all_records)
        export_csv_btn.config(command=lambda: export_handler("csv"))
        export_excel_btn.config(command=lambda: export_handler("excel"))
        export_json_btn.config(command=lambda: export_handler("json"))
        export_xml_btn.config(command=lambda: export_handler("xml"))
        export_pdf_btn.config(command=lambda: export_handler("pdf"))

        def on_tree_double_click(event):
            selected = tree.selection()
            if not selected:
                return
            values = tree.item(selected[0])["values"]
            if not values or len(values) < 2:
                return
            record_id = values[-1]
            try:
                row = db.fetch_metadata_by_id(record_id)
            except Exception:
                row = None
            if not row:
                messagebox.showerror("Load Error", "Could not load record from database.")
                return

            self.file_path = row[1]
            full_meta_json = row[7]
            try:
                self.extracted_metadata = json.loads(full_meta_json) if isinstance(full_meta_json, str) else (full_meta_json or {})
            except Exception:
                self.extracted_metadata = {}

            if risk_analyzer and isinstance(self.extracted_metadata, dict):
                try:
                    self.risk_analysis = risk_analyzer.analyze_metadata(
                        self.extracted_metadata,
                        self.file_path,
                        fallback_timestamps=self._get_timeline_fallbacks(
                            extracted_at=row[5] if len(row) > 5 else None,
                            modified_on=row[6] if len(row) > 6 else None,
                        ),
                    )
                except Exception:
                    self.risk_analysis = None

            def humanize_local(dt_str: str) -> str:
                if not dt_str:
                    return ""
                try:
                    from datetime import datetime

                    return datetime.fromisoformat(dt_str).strftime("%b %d, %Y %I:%M %p")
                except Exception:
                    return dt_str

            if self.c1_text:
                self.c1_text.config(state=NORMAL)
                self.c1_text.delete(1.0, END)
                self.c1_text.insert(END, "File Information\n", "header")
                self.c1_text.insert(END, "\n")
                self.c1_text.insert(END, f"Filename:  {row[2]}\n", "bold")
                self.c1_text.insert(END, f"Path:  {row[1]}\n", "bold")
                self.c1_text.insert(END, f"Type:  {row[4]}\n", "bold")
                self.c1_text.insert(END, f"Size:  {row[3]}\n", "bold")
                self.c1_text.insert(END, f"Extracted At:  {humanize_local(row[5])}\n", "bold")
                self.c1_text.insert(END, f"Modified On:  {humanize_local(row[6])}\n\n", "bold")
                if isinstance(self.extracted_metadata, dict):
                    for k, v in self.extracted_metadata.items():
                        self.c1_text.insert(END, f"{k}: {v}\n")
                else:
                    self.c1_text.insert(END, f"{self.extracted_metadata}\n")
                self.c1_text.config(state=DISABLED)

            try:
                if self.nb_widget is not None:
                    tabs = self.nb_widget.tabs()
                    if tabs:
                        self.nb_widget.select(tabs[0])
            except Exception:
                pass

        tree.bind("<Double-1>", on_tree_double_click)

        load_data()
        self.history_refresh = load_data

    def _build_risk_tab(self, tab5: Frame) -> None:
        """Construct Risk analyzer tab using stacked charts on left and summary panel on right."""
        container = Frame(tab5, bg="#ffffff", relief=SOLID, bd=1)
        container.pack(fill=BOTH, expand=True, padx=8, pady=8)

        left_panel = Frame(container, bg="#ffffff")
        left_panel.pack(side=LEFT, fill=BOTH, expand=True, padx=(10, 8), pady=10)

        right_column = Frame(container, bg="#ffffff", width=340)
        right_column.pack(side=RIGHT, fill=BOTH, expand=False, padx=(8, 10), pady=10)
        right_column.pack_propagate(False)

        Label(left_panel, text="Risk Meter", bg="#ffffff", font=("Segoe UI", 11, "bold"), fg="#1a1a1a", anchor=W).pack(fill=X, padx=2, pady=(0, 4))
        risk_meter_frame = Frame(left_panel, bg="#ffffff", relief=SOLID, bd=1, height=200)
        risk_meter_frame.pack(fill=X, expand=False)
        risk_meter_frame.pack_propagate(False)

        Label(left_panel, text="Forensic Timeline", bg="#ffffff", font=("Segoe UI", 11, "bold"), fg="#1a1a1a", anchor=W).pack(fill=X, padx=2, pady=(12, 4))
        timeline_frame = Frame(left_panel, bg="#ffffff", relief=SOLID, bd=1)
        timeline_frame.pack(fill=BOTH, expand=True)

        Label(right_column, text="Comments", bg="#ffffff", font=("Segoe UI", 11, "bold"), fg="#1a1a1a", anchor=W).pack(fill=X, padx=2, pady=(0, 4))
        comments_frame = Frame(right_column, bg="#ffffff", relief=SOLID, bd=1)
        comments_frame.pack(fill=BOTH, expand=True)

        self.risk_chart_canvas = FigureCanvasTkAgg(Figure(figsize=(6.0, 2.4), facecolor="white"), master=risk_meter_frame)
        self.risk_chart_canvas.get_tk_widget().pack(fill=BOTH, expand=True, padx=8, pady=8)

        self.timeline_chart_canvas = FigureCanvasTkAgg(Figure(figsize=(6.0, 2.6), facecolor="white"), master=timeline_frame)
        self.timeline_chart_canvas.get_tk_widget().pack(fill=BOTH, expand=True, padx=8, pady=8)

        self.risk_summary_text = scrolledtext.ScrolledText(comments_frame, wrap=WORD, bg="#f5f5f5", font=("Segoe UI", 10), fg="#333333", bd=0, relief=FLAT, padx=10, pady=10)
        self.risk_summary_text.pack(fill=BOTH, expand=True)
        self.risk_summary_text.config(state=DISABLED)

        self._render_risk_analysis(None)

    def _render_risk_analysis(self, analysis: dict | None) -> None:
        """Render risk gauge, reasons and timeline chart in Risk analyzer tab."""
        if self.risk_summary_text and self.risk_summary_text.winfo_exists():
            self.risk_summary_text.config(state=NORMAL)
            self.risk_summary_text.delete(1.0, END)

        if not analysis:
            if self.risk_chart_canvas:
                fig = Figure(figsize=(6.0, 2.4), facecolor="white")
                ax = fig.add_subplot(111)
                ax.axis("off")
                ax.text(0.5, 0.5, "No risk scan available.\nExtract metadata to analyze.", ha="center", va="center", fontsize=11)
                self.risk_chart_canvas.figure = fig
                self.risk_chart_canvas.draw()

            if self.timeline_chart_canvas:
                fig = Figure(figsize=(6.0, 2.6), facecolor="white")
                ax = fig.add_subplot(111)
                ax.axis("off")
                ax.text(0.5, 0.5, "No timeline events available.", ha="center", va="center", fontsize=11)
                self.timeline_chart_canvas.figure = fig
                self.timeline_chart_canvas.draw()

            if self.risk_summary_text and self.risk_summary_text.winfo_exists():
                self.risk_summary_text.insert(END, "Risk Level: N/A\nRisk Score: N/A\n\nRun extraction to view risk reasons and forensic timeline.")
                self.risk_summary_text.config(state=DISABLED)
            return

        score = int(analysis.get("risk_score", 0))
        level = analysis.get("risk_level", "LOW")
        reasons = analysis.get("reasons", [])
        timeline = analysis.get("timeline", [])
        anomalies = analysis.get("anomalies", [])

        if self.risk_chart_canvas:
            fig = Figure(figsize=(6.0, 2.4), facecolor="white")
            ax = fig.add_subplot(111)
            color_map = {"LOW": "#2ecc71", "MEDIUM": "#f39c12", "HIGH": "#e74c3c"}
            risk_color = color_map.get(level, "#3498db")
            
            # Full semicircle fill with solid color based on risk level
            full_fill = plt.matplotlib.patches.Wedge((0, 0), 1.0, 0, 180, width=1.0, facecolor=risk_color, edgecolor="none", alpha=0.85, zorder=2)
            ax.add_patch(full_fill)
            
            # Semicircle outline
            outline = plt.matplotlib.patches.Wedge((0, 0), 1.0, 0, 180, width=0.04, facecolor="none", edgecolor="#9ca3af", zorder=3)
            ax.add_patch(outline)
            ax.plot([1, -1], [0, 0], color="#9ca3af", linewidth=2, zorder=3)

            # Center labels - moved upward
            ax.text(0, 0.35, f"{score}%", ha="center", va="center", fontsize=30, weight="bold", color="#1f2937")
            ax.text(0, 0.10, f"Risk: {level}", ha="center", va="center", fontsize=12, color="#4b5563")

            ax.set_title("Privacy Risk Gauge", fontsize=11, weight="bold", y=0.95, pad=2)
            ax.set_xlim(-1.25, 1.25)
            ax.set_ylim(-0.25, 1.25)
            ax.axis("off")
            self.risk_chart_canvas.figure = fig
            self.risk_chart_canvas.draw()

        if self.timeline_chart_canvas:
            fig = Figure(figsize=(6.0, 2.6), facecolor="white")
            ax = fig.add_subplot(111)
            if timeline:
                # Convert timeline to trend chart
                from datetime import datetime
                
                # Parse timestamps and sort
                events_with_dates = []
                for event in timeline:
                    try:
                        ts_str = event.get("timestamp", "")
                        # Try to parse various date formats
                        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%b %d, %Y"]:
                            try:
                                dt = datetime.strptime(ts_str[:19], fmt[:19])
                                events_with_dates.append((dt, event.get("event", "")))
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass
                
                if events_with_dates:
                    # Group events by date and collect event names
                    from collections import defaultdict
                    date_events = defaultdict(list)
                    for dt, event_name in events_with_dates:
                        date_key = dt.date()
                        date_events[date_key].append(event_name)
                    
                    # Sort by date
                    sorted_dates = sorted(date_events.keys())
                    counts = [len(date_events[d]) for d in sorted_dates]
                    
                    # Get first event name for each date
                    event_labels = []
                    for d in sorted_dates:
                        events = date_events[d]
                        # Prioritize showing specific event types
                        label = events[0] if events else ""
                        # Clean up the label - capitalize and shorten common terms
                        label = label.replace("_", " ").title()
                        if "create" in label.lower():
                            label = "Creation"
                        elif "modif" in label.lower():
                            label = "Modification"
                        elif "extract" in label.lower():
                            label = "Extraction"
                        event_labels.append(label)
                    
                    # Convert dates to strings for display
                    full_date_labels = [d.strftime("%Y-%m-%d") for d in sorted_dates]
                    x_vals = list(range(len(sorted_dates)))
                    
                    # Plot line chart with area fill
                    ax.fill_between(x_vals, counts, alpha=0.4, color="#6b9effe6", zorder=1)
                    ax.plot(x_vals, counts, color="#4facfe", linewidth=2.5, marker="o", markersize=8, zorder=2)
                    
                    # Label each node with date and event type
                    for x, count, full_date, event_label in zip(x_vals, counts, full_date_labels, event_labels):
                        # Show date on top
                        ax.text(x, count + 0.2, full_date, ha="center", va="bottom", fontsize=8, color="#333333", weight="bold")
                        # Show event type below the date (slightly lower)
                        if event_label:
                            ax.text(x, count + 0.05, event_label, ha="center", va="bottom", fontsize=7, color="#666666", style="italic")
                    
                    # Styling - hide x-axis labels and y-axis
                    ax.set_xticks([])
                    ax.set_yticks([])
                    ax.grid(axis="y", alpha=0.15, linestyle="-")
                    ax.spines["top"].set_visible(False)
                    ax.spines["right"].set_visible(False)
                    ax.spines["left"].set_visible(False)
                else:
                    ax.axis("off")
                    ax.text(0.5, 0.5, "Unable to parse timeline dates.", ha="center", va="center", fontsize=10)
            else:
                ax.axis("off")
                ax.text(0.5, 0.5, "No timeline events discovered from metadata.", ha="center", va="center", fontsize=10)
            fig.tight_layout()
            self.timeline_chart_canvas.figure = fig
            self.timeline_chart_canvas.draw()

        if self.risk_summary_text and self.risk_summary_text.winfo_exists():
            self.risk_summary_text.insert(END, f"Risk Level: {level}\n")
            self.risk_summary_text.insert(END, f"Risk Score: {score}/100\n")
            self.risk_summary_text.insert(END, f"Timeline Events: {len(timeline)}\n")
            self.risk_summary_text.insert(END, f"Anomalies: {len(anomalies)}\n\n")

            self.risk_summary_text.insert(END, "Why this risk:\n")
            for reason in reasons:
                self.risk_summary_text.insert(END, f"• {reason}\n")

            if self.risk_batch_summary:
                counts = self.risk_batch_summary.get("risk_counts", {})
                self.risk_summary_text.insert(END, "\nBatch Summary:\n")
                self.risk_summary_text.insert(END, f"• LOW: {counts.get('LOW', 0)}\n")
                self.risk_summary_text.insert(END, f"• MEDIUM: {counts.get('MEDIUM', 0)}\n")
                self.risk_summary_text.insert(END, f"• HIGH: {counts.get('HIGH', 0)}\n")

            self.risk_summary_text.config(state=DISABLED)

    # ------------------------------------------------------------------
    # Tab and editor helpers
    # ------------------------------------------------------------------
    def _on_tab_changed(self, event, tab2: Frame, tab3: Frame, tab5: Frame) -> None:
        """Handle notebook tab changes for refresh logic.
        
        Updates history data when history tab is activated.
        
        Args:
            event: Tkinter event object from tab changed event.
            tab2 (Frame): Editor tab frame.
            tab3 (Frame): History tab frame.
            tab5 (Frame): Risk analyzer tab frame.
        """
        try:
            current = self.nb_widget.select()
            if current == str(tab3):
                if callable(self.history_refresh):
                    self.history_refresh()
            elif current == str(tab5):
                self._render_risk_analysis(self.risk_analysis)
            elif current == str(tab2):
                if not self.file_path or not self.extracted_metadata:
                    messagebox.showwarning("No Data", "Please extract metadata first.")
                    first_tab = self.nb_widget.tabs()[0]
                    self.nb_widget.select(first_tab)
        except Exception:
            pass

    def _populate_editor_fields(self, metadata: dict) -> None:
        """Populate editor UI with metadata key-value entry fields.
        
        Creates scrollable frame with Entry widgets for editing metadata.
        
        Args:
            metadata (dict): Dictionary of metadata to populate fields.
        """
        self._clear_editor_fields()
        if not metadata or not isinstance(metadata, dict):
            return
        for key, value in metadata.items():
            field_frame = Frame(self.editor_entry_frame, bg="#ffffff")
            field_frame.pack(fill=X, padx=15, pady=8)

            label = Label(field_frame, text=f"{key}:", bg="#ffffff", font=("Segoe UI", 10, "bold"), fg="#1a1a1a", width=20, anchor=W)
            label.pack(side=LEFT, padx=(0, 10))

            entry = ttk.Entry(field_frame, font=("Segoe UI", 10), width=50)
            entry.pack(side=LEFT, fill=X, expand=True)
            entry.insert(0, str(value))
            if not self._is_editable_field(key):
                entry.state(["disabled"])

            self.editor_entry_fields[key] = entry

    def _clear_editor_fields(self) -> None:
        """Clear all metadata entry fields from the editor."""
        for widget in self.editor_entry_frame.winfo_children():
            widget.destroy()
        self.editor_entry_fields.clear()

    def _is_editable_field(self, field_name: str) -> bool:
        """Check if a field is user-editable.
        
        Args:
            field_name (str): Name of the field to check.
            
        Returns:
            bool: True if field is editable, False if it's read-only.
        """
        return field_name not in self.NON_EDITABLE_FIELDS

    def _show_welcome_text(self) -> None:
        """Display welcome message in the metadata text widget."""
        if not self.c1_text:
            return
        self.c1_text.config(state=NORMAL)
        self.c1_text.delete(1.0, END)
        self.c1_text.insert(END, "Welcome to TraceLens: A Comprehensive Metadata Analysis Toolkit\n", "header")
        self.c1_text.insert(END, "\nThis tool allows you to extract & edit metadata from various file types including images, documents, and audio files.\n\n")
        self.c1_text.insert(END, "Getting Started:\n", "bold")
        self.c1_text.insert(END, "1. Click 'Choose File' to select a file\n2. Click 'Extract' to analyze its metadata\n3. Use 'Generate report' to export the results\n\n")
        self.c1_text.insert(END, "For more information, refer to the Help section in the menu bar.", "bold")
        self.c1_text.config(state=DISABLED)

    def _get_timeline_fallbacks(self, extracted_at: str | None = None, modified_on: str | None = None) -> dict:
        """Build fallback timestamps when metadata has no timeline fields."""
        fallback = {}
        if self.file_path and os.path.exists(self.file_path):
            try:
                fallback["Created Date"] = datetime.fromtimestamp(os.path.getctime(self.file_path)).isoformat(sep=" ", timespec="seconds")
            except Exception:
                pass
            try:
                fallback["Modified Date"] = datetime.fromtimestamp(os.path.getmtime(self.file_path)).isoformat(sep=" ", timespec="seconds")
            except Exception:
                pass

        if modified_on and "Modified Date" not in fallback:
            fallback["Modified Date"] = modified_on

        fallback["Extraction Date"] = extracted_at or datetime.now().isoformat(sep=" ", timespec="seconds")
        return fallback

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------
    def set_status(self, message: str) -> None:
        """Update the status bar with a message.
        
        Args:
            message (str): Status message to display.
        """
        if self.status_var:
            self.status_var.set(message)

    def _display_extracted_metadata(self, metadata, file_path: str, db_row) -> None:
        """Display extracted metadata in the text widget.
        
        Formats and displays metadata with file information and timestamps.
        
        Args:
            metadata (dict): Dictionary of extracted metadata.
            file_path (str): Path to the analyzed file.
            db_row (tuple): Database row containing extraction timestamps.
        """
        if not self.c1_text:
            return

        self.c1_text.config(state=NORMAL)
        self.c1_text.delete(1.0, END)
        self.c1_text.insert(END, "Extracted Metadata\n", "header")
        self.c1_text.insert(END, f"File: {os.path.basename(file_path)}\n\n", "bold")

        if isinstance(metadata, dict):
            if "Error" in metadata:
                self.c1_text.insert(END, f"Error: {metadata['Error']}\n", "bold")
            else:
                for key, value in metadata.items():
                    self.c1_text.insert(END, f"{key}: ", "bold")
                    self.c1_text.insert(END, f"{value}\n")
        else:
            self.c1_text.insert(END, str(metadata))

        if db_row:
            def _fmt(dt_str):
                if not dt_str:
                    return ""
                try:
                    from datetime import datetime

                    return datetime.fromisoformat(dt_str).strftime("%b %d, %Y %I:%M %p")
                except Exception:
                    return dt_str

            extracted_at_disp = _fmt(db_row[5]) if len(db_row) > 5 else ""
            modified_on_disp = _fmt(db_row[6]) if len(db_row) > 6 else ""

            self.c1_text.insert(END, "\n")
            self.c1_text.insert(END, "Extracted At: ", "bold")
            self.c1_text.insert(END, f"{extracted_at_disp}\n")
            self.c1_text.insert(END, "Modified On: ", "bold")
            self.c1_text.insert(END, f"{modified_on_disp}\n")

        self.c1_text.config(state=DISABLED)

    # ------------------------------------------------------------------
    # Core actions
    # ------------------------------------------------------------------
    def extract_metadata(self) -> None:
        """Extract metadata from the selected file and display results.
        
        Calls the extractor module to analyze the file and store metadata in the database.
        Updates the display with extracted information.
        """
        if not self.file_path:
            messagebox.showwarning("No File Selected", "Please choose a file first.")
            return

        if not extractor:
            messagebox.showerror("Error", "Extractor module not available.")
            return

        try:
            if self.progress_bar:
                self.progress_bar.start()

            self.set_status("Extracting metadata...")
            self.root.update()

            self.extracted_metadata, db_row = extractor.extract_and_store(self.file_path)

            if risk_analyzer and isinstance(self.extracted_metadata, dict) and "Error" not in self.extracted_metadata:
                try:
                    self.risk_analysis = risk_analyzer.analyze_metadata(
                        self.extracted_metadata,
                        self.file_path,
                        fallback_timestamps=self._get_timeline_fallbacks(extracted_at=datetime.now().isoformat(sep=" ", timespec="seconds")),
                    )
                except Exception:
                    self.risk_analysis = None
            else:
                self.risk_analysis = None

            if self.progress_bar:
                self.progress_bar.stop()

            self._display_extracted_metadata(self.extracted_metadata, self.file_path, db_row)
            self._render_risk_analysis(self.risk_analysis)

            if isinstance(self.extracted_metadata, dict) and "Error" not in self.extracted_metadata:
                self.set_status(f"Successfully extracted {len(self.extracted_metadata)} metadata fields")
            else:
                self.set_status("Extraction completed")

            try:
                if callable(self.history_refresh):
                    self.history_refresh()
            except Exception:
                pass

        except Exception as e:
            if self.progress_bar:
                self.progress_bar.stop()
            self.set_status(f"Extraction error: {str(e)}")
            messagebox.showerror("Extraction Error", f"Failed to extract metadata: {str(e)}")

    def generate_report(self) -> None:
        """Generate a metadata report and display in preview tab.
        
        Creates formatted report text from extracted metadata and updates the preview panel.
        """
        if not self.extracted_metadata or not self.file_path:
            messagebox.showwarning("No Data", "Please extract metadata first before generating a report.")
            return
        try:
            if risk_analyzer and isinstance(self.extracted_metadata, dict):
                self.risk_analysis = risk_analyzer.analyze_metadata(
                    self.extracted_metadata,
                    self.file_path,
                    fallback_timestamps=self._get_timeline_fallbacks(extracted_at=datetime.now().isoformat(sep=" ", timespec="seconds")),
                )
            metadata_text = report.generate_report_text(
                self.extracted_metadata,
                self.file_path,
                risk_analysis=self.risk_analysis,
                batch_summary=self.risk_batch_summary,
            )
            self.update_report_preview(metadata_text)
            self.set_status("Report preview ready")
        except Exception as e:
            self.set_status(f"Report generation error: {str(e)}")
            messagebox.showerror("Report Error", f"Failed to generate report: {str(e)}")

    def open_editor_with_current_metadata(self) -> None:
        """Open editor tab with current metadata loaded for editing.
        
        Populates editor fields with current metadata and switches to the editor tab.
        """
        if not self.extracted_metadata or not self.file_path:
            messagebox.showwarning("No Data", "Please extract metadata first.")
            try:
                if self.nb_widget is not None:
                    tabs = self.nb_widget.tabs()
                    if tabs:
                        self.nb_widget.select(tabs[0])
            except Exception:
                pass
            return

        if self.extracted_metadata and isinstance(self.extracted_metadata, dict):
            self._populate_editor_fields(self.extracted_metadata)
            self.editor_status.config(text="", fg="#555555")

        if self.nb_widget is not None and self.tab2_ref is not None:
            self.nb_widget.select(self.tab2_ref)

    def open_risk_analyzer_with_scan(self) -> None:
        """Open Risk analyzer tab and scan current file metadata for privacy/forensic risk."""
        if not self.file_path:
            messagebox.showwarning("No File Selected", "Please choose a file first.")
            return

        if not risk_analyzer:
            messagebox.showerror("Error", "Risk analyzer module not available.")
            return

        if not self.extracted_metadata or not isinstance(self.extracted_metadata, dict) or "Error" in self.extracted_metadata:
            if not extractor:
                messagebox.showerror("Error", "Extractor module not available.")
                return
            try:
                self.set_status("Extracting metadata for risk scan...")
                if self.progress_bar:
                    self.progress_bar.start()
                self.extracted_metadata, db_row = extractor.extract_and_store(self.file_path)
                if self.progress_bar:
                    self.progress_bar.stop()
                self._display_extracted_metadata(self.extracted_metadata, self.file_path, db_row)
                if callable(self.history_refresh):
                    self.history_refresh()
            except Exception as exc:
                if self.progress_bar:
                    self.progress_bar.stop()
                messagebox.showerror("Risk Scan Error", f"Failed to extract metadata before risk scan: {exc}")
                return

        try:
            self.risk_analysis = risk_analyzer.analyze_metadata(
                self.extracted_metadata,
                self.file_path,
                fallback_timestamps=self._get_timeline_fallbacks(extracted_at=datetime.now().isoformat(sep=" ", timespec="seconds")),
            )
            self._render_risk_analysis(self.risk_analysis)

            if self.nb_widget is not None and self.tab5_ref is not None:
                self.nb_widget.select(self.tab5_ref)

            level = self.risk_analysis.get("risk_level", "N/A") if isinstance(self.risk_analysis, dict) else "N/A"
            self.set_status(f"Risk scan complete: {level}")
        except Exception as exc:
            messagebox.showerror("Risk Scan Error", f"Failed to analyze risk: {exc}")

    def choose_file(self) -> None:
        """Open file dialog for user to select a file to analyze.
        
        Sets self.file_path and updates status bar with selected file.
        """
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
            self.file_path = selected_file
            self.extracted_metadata = {}
            self.risk_analysis = None
            if self.progress_bar:
                self.progress_bar.start()
                self.root.after(2000, lambda: self.progress_bar.stop())
            self.set_status(f"File selected: {os.path.basename(selected_file)}")
            if self.c1_text:
                self.c1_text.config(state=NORMAL)
                self.c1_text.delete(1.0, END)
                self.c1_text.insert(END, "File Information\n", "header")
                self.c1_text.insert(END, "\n")
                self.c1_text.insert(END, f"Filename:  {os.path.basename(selected_file)}\n", "bold")
                self.c1_text.insert(END, f"Path:  {selected_file}\n", "bold")
                self.c1_text.insert(END, "\nStatus:  Ready for extraction\n\n", "bold")
                self.c1_text.insert(END, "Click 'Extract' to analyze the file metadata.", "bold")
                self.c1_text.config(state=DISABLED)

    def update_report_preview(self, text: str) -> None:
        """Update the report preview panel with formatted text.
        
        Displays report text in the preview tab.
        
        Args:
            text (str): Report text to display in preview.
        """
        self.report_last_text = text or ""

        def _show_text_preview():
            try:
                # Hide image preview scrollbar
                if self.preview_scrollbar and self.preview_scrollbar.winfo_exists():
                    self.preview_scrollbar.pack_forget()
            except Exception:
                pass

            try:
                if self.report_preview and self.report_preview.winfo_exists():
                    self.report_preview.pack(fill=BOTH, expand=True)
                    self.report_preview.config(state=NORMAL)
                    self.report_preview.delete(1.0, END)
                    self.report_preview.insert(END, self.report_last_text)
                    self.report_preview.config(state=DISABLED)
            except Exception as e:  # pragma: no cover - UI fallback
                print(f"Error showing text preview: {e}")

        def _show_image_preview(pil_img):
            try:
                try:
                    from PIL import ImageTk, Image
                except ImportError:
                    _show_text_preview()
                    return

                # Store original image for zoom operations
                self.preview_base_image = pil_img
                self.preview_image_zoom = 1.0  # Reset zoom when new image is loaded
                
                max_width = self.window_width - 280 if self.window_width else 900

                img_width, img_height = pil_img.size
                width_ratio = max_width / img_width
                # Fit preview to width, keep full height scrollable for multi-page reports.
                scale_ratio = min(width_ratio, 1.0)

                if scale_ratio < 1.0:
                    new_width = int(img_width * scale_ratio)
                    new_height = int(img_height * scale_ratio)
                    pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    img_width, img_height = new_width, new_height

                self.report_preview_tk_img = ImageTk.PhotoImage(pil_img)

                # Hide text preview
                if self.report_preview and self.report_preview.winfo_exists():
                    self.report_preview.pack_forget()

                # Show image preview in canvas
                if self.report_image_label and self.report_image_label.winfo_exists():
                    self.report_image_label.config(image=self.report_preview_tk_img, bg="#e8e8e8")
                
                # Update canvas scroll region
                if self.preview_canvas and self.preview_canvas.winfo_exists():
                    self.preview_canvas.update_idletasks()
                    canvas_width = self.preview_canvas.winfo_width()
                    canvas_height = self.preview_canvas.winfo_height()
                    
                    # Keep image anchored to top-center for natural vertical scrolling.
                    self.preview_canvas.coords(self.canvas_window_id, canvas_width // 2, 10)
                    self.preview_canvas.config(scrollregion=self.preview_canvas.bbox("all"))
                    if img_height > canvas_height and self.preview_scrollbar and self.preview_scrollbar.winfo_exists():
                        self.preview_scrollbar.pack(side=RIGHT, fill=Y)
                    else:
                        self.preview_scrollbar.pack_forget()
                
                # Update zoom display
                if hasattr(self, 'zoom_display_label') and self.zoom_display_label:
                    self.zoom_display_label.config(text="100%")
                        
            except Exception as e:  # pragma: no cover - UI fallback
                print(f"Error showing image preview: {e}")
                _show_text_preview()

        def _try_render_image_from_pdf(pdf_path: str) -> bool:
            try:
                try:
                    from pdf2image import convert_from_path
                    from PIL import Image, ImageDraw
                except ImportError:
                    print("pdf2image not available")
                    return False

                poppler_path = r"C:\\poppler\\Library\\bin"
                convert_kwargs = {"dpi": 150}
                if os.path.isdir(poppler_path):
                    convert_kwargs["poppler_path"] = poppler_path

                images = convert_from_path(pdf_path, **convert_kwargs)

                if images:
                    if len(images) == 1:
                        _show_image_preview(images[0])
                        return True

                    # Stitch all PDF pages into one tall image so users can scroll through full report.
                    page_images = [img.convert("RGB") for img in images]
                    page_spacing = 24
                    max_width = max(img.width for img in page_images)
                    total_height = sum(img.height for img in page_images) + page_spacing * (len(page_images) - 1)
                    merged = Image.new("RGB", (max_width, total_height), "white")
                    draw = ImageDraw.Draw(merged)

                    y_offset = 0
                    for page_index, page_img in enumerate(page_images, start=1):
                        x_offset = (max_width - page_img.width) // 2
                        merged.paste(page_img, (x_offset, y_offset))

                        next_y_offset = y_offset + page_img.height
                        if page_index < len(page_images):
                            # Draw a separator in the spacing area between pages for visual clarity.
                            sep_y = next_y_offset + (page_spacing // 2)
                            draw.line((20, sep_y, max_width - 20, sep_y), fill=(180, 180, 180), width=2)
                            draw.text((24, sep_y - 14), f"Page {page_index + 1}", fill=(120, 120, 120))

                        y_offset = next_y_offset + page_spacing

                    _show_image_preview(merged)
                    return True
                return False
            except Exception as e:  # pragma: no cover - UI fallback
                print(f"Error rendering PDF to image: {e}")
                return False

        def _render_image_preview() -> bool:
            try:
                temp_dir = tempfile.gettempdir()
                temp_pdf = os.path.join(temp_dir, f"metadata_report_preview_{os.getpid()}.pdf")
                report.create_pdf_report_from_text(self.report_last_text, temp_pdf)
                return _try_render_image_from_pdf(temp_pdf)
            except Exception as e:  # pragma: no cover - UI fallback
                print(f"Error creating preview PDF: {e}")
                return False

        if not _render_image_preview():
            _show_text_preview()

        try:
            if self.nb_widget is not None and self.tab4_ref is not None:
                self.nb_widget.select(self.tab4_ref)
        except Exception:
            pass

    def save_report_from_preview(self) -> None:
        """Save the current report preview to a PDF file.
        
        Launches file dialog for user to choose save location.
        """
        try:
            if not self.report_last_text.strip():
                messagebox.showwarning("No Data", "There is no report content to save.")
                return
            report.save_metadata(self.report_last_text)
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save report: {str(e)}")

    def print_report_from_preview(self) -> None:
        """Send the current report preview to the default printer.
        
        Windows only - sends PDF to default printer via os.startfile.
        """
        try:
            if not self.report_last_text.strip():
                messagebox.showwarning("No Data", "There is no report content to print.")
                return
            report.print_metadata_report(self.report_last_text)
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print report: {str(e)}")

    # ------------------------------------------------------------------
    # Canvas centering helper
    # ------------------------------------------------------------------
    def _on_canvas_configure(self, event=None) -> None:
        """Center the image in canvas when canvas is configured/resized."""
        try:
            if self.preview_canvas and self.preview_canvas.winfo_exists():
                canvas_width = self.preview_canvas.winfo_width()
                canvas_height = self.preview_canvas.winfo_height()
                
                # Only center if canvas has valid dimensions
                if canvas_width > 1 and canvas_height > 1:
                    self.preview_canvas.coords(self.canvas_window_id, canvas_width // 2, 10)
                    self.preview_canvas.config(scrollregion=self.preview_canvas.bbox("all"))
                    if self.report_image_label and self.report_image_label.winfo_exists():
                        label_height = self.report_image_label.winfo_height()
                        if label_height > canvas_height and self.preview_scrollbar and self.preview_scrollbar.winfo_exists():
                            self.preview_scrollbar.pack(side=RIGHT, fill=Y)
                        elif self.preview_scrollbar and self.preview_scrollbar.winfo_exists():
                            self.preview_scrollbar.pack_forget()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Image zoom controls
    # ------------------------------------------------------------------
    def zoom_in_image(self) -> None:
        """Zoom in on the preview image by 20%."""
        if self.preview_base_image is None:
            return
        
        self.preview_image_zoom = min(self.preview_image_zoom + 0.2, 2.0)  # Max 200%
        self._apply_image_zoom()
    
    def zoom_out_image(self) -> None:
        """Zoom out on the preview image by 20%."""
        if self.preview_base_image is None:
            return
        
        self.preview_image_zoom = max(self.preview_image_zoom - 0.2, 0.4)  # Min 40%
        self._apply_image_zoom()
    
    def reset_zoom_image(self) -> None:
        """Reset image zoom to 100%."""
        if self.preview_base_image is None:
            return
        
        self.preview_image_zoom = 1.0
        self._apply_image_zoom()
    
    def _apply_image_zoom(self) -> None:
        """Apply the current zoom level to the preview image."""
        try:
            from PIL import ImageTk, Image
            
            if self.preview_base_image is None:
                return
            
            # Calculate dimensions with zoom
            max_width = self.window_width - 280 if self.window_width else 900
            
            img_width, img_height = self.preview_base_image.size
            width_ratio = max_width / img_width
            base_scale_ratio = min(width_ratio, 1.0)
            
            # Apply base scale and zoom
            final_scale = base_scale_ratio * self.preview_image_zoom
            new_width = int(img_width * final_scale)
            new_height = int(img_height * final_scale)
            
            # Resize image
            resized_img = self.preview_base_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.report_preview_tk_img = ImageTk.PhotoImage(resized_img)
            
            # Update label
            if self.report_image_label and self.report_image_label.winfo_exists():
                self.report_image_label.config(image=self.report_preview_tk_img)
            
            # Update canvas scroll region and center the image
            if self.preview_canvas and self.preview_canvas.winfo_exists():
                self.preview_canvas.update_idletasks()
                canvas_width = self.preview_canvas.winfo_width()
                canvas_height = self.preview_canvas.winfo_height()
                
                # Keep image anchored to top-center so full document can be scrolled.
                x_center = canvas_width // 2
                y_center = 10
                self.preview_canvas.coords(self.canvas_window_id, x_center, y_center)
                
                # Set scroll region to accommodate larger zoomed images
                scroll_width = max(canvas_width, new_width)
                scroll_height = max(canvas_height, new_height)
                self.preview_canvas.config(scrollregion=(0, 0, scroll_width, scroll_height))
                
                if new_height > canvas_height and self.preview_scrollbar and self.preview_scrollbar.winfo_exists():
                    self.preview_scrollbar.pack(side=RIGHT, fill=Y)
                elif self.preview_scrollbar and self.preview_scrollbar.winfo_exists():
                    self.preview_scrollbar.pack_forget()
            
            # Update zoom display
            if hasattr(self, 'zoom_display_label') and self.zoom_display_label:
                self.zoom_display_label.config(text=f"{int(self.preview_image_zoom * 100)}%")
            
            self.set_status(f"Image zoom: {int(self.preview_image_zoom * 100)}%")
            
        except Exception as e:
            print(f"Error applying image zoom: {e}")

    # ------------------------------------------------------------------
    # Editor actions
    # ------------------------------------------------------------------
    def save_editor_changes(self) -> None:
        """Save edited metadata from editor fields to database and file.
        
        Validates edited metadata, writes to database, and optionally to the source file.
        """
        if not self.file_path or not self.extracted_metadata:
            messagebox.showwarning("No Data", "No metadata loaded to save.")
            return

        try:
            edited_metadata = {}
            headers = {}
            
            for field_name, entry_widget in self.editor_entry_fields.items():
                value = entry_widget.get().strip()
                if value:
                    # Separate headers from regular metadata
                    if field_name in self.NON_EDITABLE_FIELDS:
                        headers[field_name] = value
                    else:
                        edited_metadata[field_name] = value

            # Ensure headers are populated from file info if not already present
            if not headers.get("File Name") and self.file_path:
                headers["File Name"] = os.path.basename(self.file_path)
            if not headers.get("File Size") and self.file_path:
                try:
                    headers["File Size"] = str(os.path.getsize(self.file_path))
                except Exception:
                    pass
            if not headers.get("File Type") and self.file_path:
                headers["File Type"] = os.path.splitext(self.file_path)[1].lstrip('.')

            if not edited_metadata:
                messagebox.showwarning("Empty Metadata", "Please enter at least one metadata field.")
                return

            valid, error_msg = editor.validate_metadata({"metadata": edited_metadata, "headers": headers})
            if not valid:
                self.editor_status.config(text=error_msg, fg="#dc3545")
                messagebox.showerror("Validation Error", error_msg)
                return

            db_success, db_message = db.save_edited_metadata(self.file_path, {"metadata": edited_metadata, "headers": headers})
            if not db_success:
                self.editor_status.config(text=db_message, fg="#dc3545")
                messagebox.showerror("Database Error", db_message)
                return

            file_success, file_message = editor.write_metadata_to_file(self.file_path, edited_metadata)

            self.extracted_metadata = edited_metadata
            if risk_analyzer:
                try:
                    self.risk_analysis = risk_analyzer.analyze_metadata(
                        self.extracted_metadata,
                        self.file_path,
                        fallback_timestamps=self._get_timeline_fallbacks(extracted_at=datetime.now().isoformat(sep=" ", timespec="seconds")),
                    )
                except Exception:
                    self.risk_analysis = None
            self._render_risk_analysis(self.risk_analysis)

            if file_success:
                self.editor_status.config(text="Saved to database and file", fg="#28a745")
                messagebox.showinfo("Success", "✓ Database updated\n✓ File metadata updated")
            else:
                self.editor_status.config(text="Saved to database only", fg="#ff8c00")
                messagebox.showwarning("Partial Success", f"✓ Database updated\n⚠ File: {file_message}")

            try:
                if callable(self.history_refresh):
                    self.history_refresh()
            except Exception:
                pass

        except Exception as e:
            error_msg = f"Failed to save: {str(e)}"
            self.editor_status.config(text=error_msg, fg="#dc3545")
            messagebox.showerror("Error", error_msg)

    def cancel_editor_changes(self) -> None:
        """Discard editor changes and reload original extracted metadata.
        
        Clears editor fields and resets status without saving changes.
        """
        if not self.file_path or not self.extracted_metadata:
            self._clear_editor_fields()
            self.editor_status.config(text="", fg="#555555")
            return

        if messagebox.askyesno("Cancel Changes", "Discard all changes and reload original metadata?"):
            try:
                self._populate_editor_fields(self.extracted_metadata)
                self.editor_status.config(text="Changes discarded", fg="#555555")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to reload: {str(e)}")

    def add_metadata_field(self) -> None:
        """Open dialog to add custom metadata field to the editor.
        
        Allows user to input a key-value pair for new metadata (e.g., GPS location for images).
        Adds the new field to the editor entry fields and updates the display.
        """
        if not self.file_path or not self.extracted_metadata:
            messagebox.showwarning("No Data", "Please extract metadata first before adding custom fields.")
            return

        # Create dialog window
        dialog = Toplevel(self.root)
        dialog.title("Add Metadata Field")
        dialog.geometry("550x320")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.transient(self.root)
        
        # Center dialog on parent window
        dialog.update_idletasks()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        
        dialog_width = dialog.winfo_width()
        dialog_height = dialog.winfo_height()
        
        center_x = parent_x + (parent_width // 2) - (dialog_width // 2)
        center_y = parent_y + (parent_height // 2) - (dialog_height // 2)
        
        dialog.geometry(f"+{center_x}+{center_y}")
        
        # Create main frame with scrolling capability
        main_frame = Frame(dialog, bg="#ffffff", padx=25, pady=25)
        main_frame.pack(fill=BOTH, expand=True)
        
        # Title label
        title_label = Label(main_frame, text="Add Custom Metadata", bg="#ffffff", font=("Segoe UI", 13, "bold"), fg="#1a1a1a")
        title_label.pack(anchor=W, pady=(0, 20))
        
        # Description label
        desc_label = Label(main_frame, text="Add new metadata field for your file (e.g., GPS location, camera info, custom tags)", bg="#ffffff", font=("Segoe UI", 9), fg="#666666", wraplength=500, justify=LEFT)
        desc_label.pack(anchor=W, pady=(0, 18))
        
        # Field name label and entry
        field_name_label = Label(main_frame, text="Field Name:", bg="#ffffff", font=("Segoe UI", 11, "bold"), fg="#333333")
        field_name_label.pack(anchor=W, pady=(0, 8))
        
        field_name_entry = ttk.Entry(main_frame, font=("Segoe UI", 10), width=50)
        field_name_entry.pack(fill=X, pady=(0, 16))
        field_name_entry.focus()
        
        # Field value label and entry
        field_value_label = Label(main_frame, text="Field Value:", bg="#ffffff", font=("Segoe UI", 11, "bold"), fg="#333333")
        field_value_label.pack(anchor=W, pady=(0, 8))
        
        field_value_entry = ttk.Entry(main_frame, font=("Segoe UI", 10), width=50)
        field_value_entry.pack(fill=X, pady=(0, 12))
        
        # Example text
        example_label = Label(main_frame, text="Examples: GPS Latitude: 40.7128 | Camera Model: Canon EOS | Author: John Doe", bg="#ffffff", font=("Segoe UI", 9, "italic"), fg="#999999", wraplength=500, justify=LEFT)
        example_label.pack(anchor=W, pady=(0, 20))
        
        # Buttons frame
        button_frame = Frame(main_frame, bg="#ffffff")
        button_frame.pack(fill=X, pady=(10, 0))
        
        def add_field():
            field_name = field_name_entry.get().strip()
            field_value = field_value_entry.get().strip()
            
            if not field_name:
                messagebox.showwarning("Invalid Input", "Please enter a field name.")
                field_name_entry.focus()
                return
            
            if not field_value:
                messagebox.showwarning("Invalid Input", "Please enter a field value.")
                field_value_entry.focus()
                return
            
            if field_name in self.NON_EDITABLE_FIELDS:
                messagebox.showwarning("Reserved Field", f"'{field_name}' is a reserved field and cannot be modified.")
                field_name_entry.focus()
                return
            
            if field_name in self.editor_entry_fields:
                messagebox.showwarning("Duplicate Field", f"Field '{field_name}' already exists. Edit it directly or use a different name.")
                field_name_entry.focus()
                return
            
            # Add the new field to extracted metadata
            self.extracted_metadata[field_name] = field_value
            
            # Refresh the editor display
            self._populate_editor_fields(self.extracted_metadata)
            
            # Update status
            self.editor_status.config(text=f"Added new field: {field_name}", fg="#28a745")
            
            dialog.destroy()
            messagebox.showinfo("Success", f"Field '{field_name}' added successfully.\n\nDon't forget to save your changes.")
        
        def cancel_dialog():
            dialog.destroy()
        
        # Add buttons
        ttk.Button(button_frame, text="Add", command=add_field).pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_dialog).pack(side=LEFT, padx=5)

        # Allow Enter key to add field
        field_value_entry.bind("<Return>", lambda e: add_field())

    # ------------------------------------------------------------------
    # Menu handlers
    # ------------------------------------------------------------------
    def menu_new_project(self) -> None:
        if messagebox.askyesno("New Project", "Start a new project? This will clear current data."):
            self.file_path = None
            self.extracted_metadata = {}
            self.risk_analysis = None
            self.risk_batch_summary = None
            self._show_welcome_text()
            self._render_risk_analysis(None)
            self._clear_editor_fields()
            self.set_status("Ready")

    def menu_import_metadata(self) -> None:
        filepath = filedialog.askopenfilename(title="Import Metadata", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    imported_data = json.load(f)
                if isinstance(imported_data, dict):
                    self.extracted_metadata = imported_data
                    self.file_path = imported_data.get("File Path", filepath)
                    self._display_extracted_metadata(self.extracted_metadata, self.file_path, None)
                    self.set_status(f"Imported metadata from {os.path.basename(filepath)}")
                    messagebox.showinfo("Success", "Metadata imported successfully.")
                else:
                    messagebox.showerror("Error", "Invalid metadata format.")
            except Exception as e:
                messagebox.showerror("Import Error", f"Failed to import: {str(e)}")

    def menu_export_results(self) -> None:
        if not self.extracted_metadata:
            messagebox.showwarning("No Data", "Please extract metadata first.")
            return

        filepath = filedialog.asksaveasfilename(
            title="Export Metadata",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    if filepath.endswith(".json"):
                        json.dump(self.extracted_metadata, f, indent=4)
                    else:
                        for key, value in self.extracted_metadata.items():
                            f.write(f"{key}: {value}\n")
                self.set_status(f"Exported to {os.path.basename(filepath)}")
                messagebox.showinfo("Success", "Metadata exported successfully.")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export: {str(e)}")

    def menu_clear_all_data(self) -> None:
        if messagebox.askyesno("Clear Data", "Clear all extracted metadata?"):
            self.extracted_metadata = {}
            self.file_path = None
            self.risk_analysis = None
            if self.c1_text:
                self.c1_text.config(state=NORMAL)
                self.c1_text.delete(1.0, END)
                self.c1_text.insert(END, "Data cleared. Ready to start.\n")
                self.c1_text.config(state=DISABLED)
            self._render_risk_analysis(None)
            self._clear_editor_fields()
            self.set_status("Data cleared")

    def menu_copy_results(self) -> None:
        if not self.extracted_metadata:
            messagebox.showwarning("No Data", "No metadata to copy.")
            return
        try:
            text = "\n".join([f"{k}: {v}" for k, v in self.extracted_metadata.items()])
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.set_status("Metadata copied to clipboard")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy: {str(e)}")

    def menu_refresh_all(self) -> None:
        try:
            if callable(self.history_refresh):
                self.history_refresh()
            self.set_status("Data refreshed")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh: {str(e)}")

    def menu_backup_database(self) -> None:
        try:
            import shutil
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = filedialog.asksaveasfilename(
                title="Backup Database",
                defaultextension=".db",
                initialfile=f"metadata_backup_{timestamp}.db",
                filetypes=[("Database files", "*.db"), ("All files", "*.*")],
            )
            if backup_path:
                shutil.copy2("metadata.db", backup_path)
                messagebox.showinfo("Success", f"Database backed up to:\n{backup_path}")
                self.set_status("Database backed up successfully")
        except Exception as e:
            messagebox.showerror("Backup Error", f"Failed to backup database: {str(e)}")

    def menu_clear_history(self) -> None:
        if messagebox.askyesno("Clear History", "Delete all metadata history? This cannot be undone."):
            if db.clear_metadata():
                messagebox.showinfo("Success", "History cleared successfully.")
                if callable(self.history_refresh):
                    self.history_refresh()
                self.set_status("History cleared")
            else:
                messagebox.showerror("Error", "Failed to clear history.")

    def menu_show_about(self) -> None:
        about_text = (
            "TraceLens\n\n"
            "Version 1.0\n\n"
            "A comprehensive tool for extracting, editing, and analyzing\n"
            "metadata from various file types.\n\n"
            "Supports images, documents, audio files, and more.\n\n"
            "© 2026 TraceLens Project"
        )
        messagebox.showinfo("About TraceLens", about_text)

    def menu_show_documentation(self) -> None:
        doc_text = (
            "TraceLens - Quick Guide\n\n"
            "1. EXTRACTING METADATA:\n"
            "   • Click 'Choose File' or File > Open File\n"
            "   • Click 'Extract' to analyze metadata\n\n"
            "2. EDITING METADATA:\n"
            "   • Click 'Editor' button after extraction\n"
            "   • Modify editable fields\n"
            "   • Click 'Save Changes'\n\n"
            "3. GENERATING REPORTS:\n"
            "   • Click 'Generate Report' button\n"
            "   • Save or print from Preview tab\n\n"
            "4. VIEWING HISTORY:\n"
            "   • Switch to History tab\n"
            "   • Use search and filters\n"
            "   • Export or delete records\n"
        )
        messagebox.showinfo("Documentation", doc_text)

    def menu_show_shortcuts(self) -> None:
        shortcuts_text = (
            "Keyboard Shortcuts\n\n"
            "File Menu:\n"
            "  Ctrl+N  - New Project\n"
            "  Ctrl+O  - Open File\n"
            "  Ctrl+E  - Export Results\n"
            "  Alt+F4  - Exit\n\n"
            "Edit Menu:\n"
            "  Ctrl+C  - Copy Results\n"
            "  Ctrl+P  - Preferences\n\n"
            "View Menu:\n"
            "  F5      - Refresh All Data\n"
            "  F11     - Full Screen\n\n"
            "Help Menu:\n"
            "  F1      - Documentation\n"
        )
        messagebox.showinfo("Keyboard Shortcuts", shortcuts_text)

    def menu_not_implemented(self, feature_name: str) -> None:
        messagebox.showinfo("Coming Soon", f"{feature_name} is not yet implemented.")

    def menu_settings(self) -> None:
        settings_window = Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("500x400")
        settings_window.resizable(False, False)
        settings_window.transient(self.root)
        settings_window.grab_set()

        title_label = Label(settings_window, text="Application Settings", font=("Segoe UI", 14, "bold"), bg="#f5f7fa")
        title_label.pack(fill=X, padx=15, pady=(15, 10))

        settings_frame = Frame(settings_window, bg="#ffffff")
        settings_frame.pack(fill=BOTH, expand=True, padx=15, pady=10)

        Label(settings_frame, text="Display Settings", font=("Segoe UI", 11, "bold"), bg="#ffffff").pack(anchor=W, pady=(0, 8))

        theme_frame = Frame(settings_frame, bg="#ffffff")
        theme_frame.pack(fill=X, pady=5)
        Label(theme_frame, text="Theme:", bg="#ffffff", width=15, anchor=W).pack(side=LEFT)
        theme_var = StringVar(value="Light")
        ttk.Combobox(theme_frame, textvariable=theme_var, values=["Light", "Dark"], state="readonly", width=20).pack(side=LEFT)

        font_frame = Frame(settings_frame, bg="#ffffff")
        font_frame.pack(fill=X, pady=5)
        Label(font_frame, text="Font Size:", bg="#ffffff", width=15, anchor=W).pack(side=LEFT)
        font_var = StringVar(value="11")
        ttk.Combobox(font_frame, textvariable=font_var, values=["9", "10", "11", "12", "13", "14"], state="readonly", width=20).pack(side=LEFT)

        Label(settings_frame, text="Behavior Settings", font=("Segoe UI", 11, "bold"), bg="#ffffff").pack(anchor=W, pady=(15, 8))

        auto_refresh_var = BooleanVar(value=True)
        Checkbutton(settings_frame, text="Auto-refresh history on data change", variable=auto_refresh_var, bg="#ffffff").pack(anchor=W, pady=3)

        confirm_delete_var = BooleanVar(value=True)
        Checkbutton(settings_frame, text="Confirm before deleting records", variable=confirm_delete_var, bg="#ffffff").pack(anchor=W, pady=3)

        button_frame = Frame(settings_window, bg="#f5f7fa")
        button_frame.pack(fill=X, padx=15, pady=(10, 15))

        def save_settings():
            messagebox.showinfo("Settings", "Settings saved successfully!")
            settings_window.destroy()

        ttk.Button(button_frame, text="Save", command=save_settings).pack(side=RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=settings_window.destroy).pack(side=RIGHT, padx=5)

    def menu_recent_files(self) -> None:
        """Open Recent Files dialog showing last 10 extracted files with modern UI and scrollbar."""
        recent_window = Toplevel(self.root)
        recent_window.title("Recent Files")
        recent_window.config(bg="#f5f7fa")
        
        # Set window size
        window_width = 700
        window_height = 500
        
        # Center the window on the main window
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        x = main_x + (main_width - window_width) // 2
        y = main_y + (main_height - window_height) // 2
        
        recent_window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        recent_window.transient(self.root)
        recent_window.grab_set()
        recent_window.resizable(False, False)

        # Header section with modern styling
        header_frame = Frame(recent_window, bg="#0066cc", height=60)
        header_frame.pack(fill=X)
        header_frame.pack_propagate(False)
        
        Label(
            header_frame, 
            text="Recent Files", 
            font=("Segoe UI", 16, "bold"), 
            bg="#0066cc", 
            fg="white"
        ).pack(side=LEFT, padx=20, pady=15)
        
        Label(
            header_frame, 
            text="Last 10 extracted files", 
            font=("Segoe UI", 9), 
            bg="#0066cc", 
            fg="#b3d9ff"
        ).pack(side=LEFT, padx=(0, 20), pady=15)

        try:
            recent_data = db.get_recent_records(limit=10)

            # Main content frame with padding
            content_frame = Frame(recent_window, bg="#f5f7fa")
            content_frame.pack(fill=BOTH, expand=True, padx=0, pady=0)

            if not recent_data:
                # Empty state with icon
                empty_frame = Frame(content_frame, bg="#ffffff")
                empty_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)
                
                Label(
                    empty_frame, 
                    text="No Files", 
                    font=("Segoe UI", 24, "bold"), 
                    bg="#ffffff", 
                    fg="#cccccc"
                ).pack(pady=(40, 10))
                
                Label(
                    empty_frame, 
                    text="No recent files", 
                    font=("Segoe UI", 12, "bold"), 
                    bg="#ffffff", 
                    fg="#666666"
                ).pack(pady=(0, 5))
                
                Label(
                    empty_frame, 
                    text="Extract metadata from files to see them here", 
                    font=("Segoe UI", 10), 
                    bg="#ffffff", 
                    fg="#999999"
                ).pack(pady=(0, 40))
            else:
                # Scrollable frame for file list
                list_container = Frame(content_frame, bg="#f5f7fa")
                list_container.pack(fill=BOTH, expand=True, padx=20, pady=15)
                
                # Create canvas and scrollbar
                canvas = Canvas(list_container, bg="#f5f7fa", highlightthickness=0)
                scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
                scrollable_frame = Frame(canvas, bg="#f5f7fa")
                
                scrollable_frame.bind(
                    "<Configure>",
                    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
                )
                
                canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
                canvas.configure(yscrollcommand=scrollbar.set)
                
                # Pack canvas and scrollbar
                canvas.pack(side=LEFT, fill=BOTH, expand=True)
                scrollbar.pack(side=RIGHT, fill=Y)
                
                # Enable mouse wheel scrolling
                def _on_mousewheel(event):
                    delta_steps = 0
                    if hasattr(event, "delta") and event.delta:
                        delta_steps = int(-1 * (event.delta / 120))
                    elif getattr(event, "num", None) == 4:
                        delta_steps = -1
                    elif getattr(event, "num", None) == 5:
                        delta_steps = 1
                    if delta_steps:
                        canvas.yview_scroll(delta_steps, "units")

                recent_window.bind("<MouseWheel>", _on_mousewheel, add="+")
                recent_window.bind("<Button-4>", _on_mousewheel, add="+")
                recent_window.bind("<Button-5>", _on_mousewheel, add="+")
                
                # Populate file list with improved styling
                for idx, row in enumerate(recent_data, 1):
                    file_item = Frame(scrollable_frame, bg="#ffffff", relief=FLAT, bd=0)
                    file_item.pack(fill=X, pady=(0, 10), ipady=5, ipadx=5)
                    
                    # Add subtle shadow effect with border
                    file_item.config(highlightbackground="#e0e0e0", highlightthickness=1)
                    
                    # Index badge
                    index_frame = Frame(file_item, bg="#0066cc", width=40, height=40)
                    index_frame.pack(side=LEFT, padx=(10, 15), pady=10)
                    index_frame.pack_propagate(False)
                    
                    Label(
                        index_frame, 
                        text=str(idx), 
                        font=("Segoe UI", 12, "bold"), 
                        bg="#0066cc", 
                        fg="white"
                    ).place(relx=0.5, rely=0.5, anchor=CENTER)
                    
                    # File info section
                    info_frame = Frame(file_item, bg="#ffffff")
                    info_frame.pack(side=LEFT, fill=BOTH, expand=True, pady=10)
                    
                    # File name
                    Label(
                        info_frame, 
                        text=row[2], 
                        font=("Segoe UI", 11, "bold"), 
                        bg="#ffffff", 
                        fg="#1a1a1a", 
                        anchor=W
                    ).pack(fill=X, padx=0, pady=(0, 5))
                    
                    # File path
                    path_label = Label(
                        info_frame, 
                        text=f"Path: {row[1]}", 
                        font=("Segoe UI", 9), 
                        bg="#ffffff", 
                        fg="#666666", 
                        anchor=W
                    )
                    path_label.pack(fill=X, padx=0, pady=(0, 3))
                    
                    # File metadata (type, size, date)
                    meta_frame = Frame(info_frame, bg="#ffffff")
                    meta_frame.pack(fill=X, padx=0)
                    
                    Label(
                        meta_frame, 
                        text=row[4].upper(), 
                        font=("Segoe UI", 8, "bold"), 
                        bg="#e8f4fd", 
                        fg="#0066cc", 
                        relief=FLAT,
                        padx=8,
                        pady=2
                    ).pack(side=LEFT, padx=(0, 5))
                    
                    Label(
                        meta_frame, 
                        text=row[3], 
                        font=("Segoe UI", 8), 
                        bg="#f0f0f0", 
                        fg="#666666",
                        relief=FLAT,
                        padx=8,
                        pady=2
                    ).pack(side=LEFT, padx=(0, 5))
                    
                    # Extracted date (if available)
                    if len(row) > 5 and row[5]:
                        Label(
                            meta_frame, 
                            text=row[5], 
                            font=("Segoe UI", 8), 
                            bg="#f0f0f0", 
                            fg="#666666",
                            relief=FLAT,
                            padx=8,
                            pady=2
                        ).pack(side=LEFT)
                        
        except Exception as e:
            error_frame = Frame(content_frame, bg="#ffffff")
            error_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)
            
            Label(
                error_frame, 
                text="ERROR", 
                font=("Segoe UI", 24, "bold"), 
                bg="#ffffff", 
                fg="#ff6b6b"
            ).pack(pady=(40, 10))
            
            Label(
                error_frame, 
                text="Error Loading Recent Files", 
                font=("Segoe UI", 12, "bold"), 
                bg="#ffffff", 
                fg="#ff6b6b"
            ).pack(pady=(0, 5))
            
            Label(
                error_frame, 
                text=str(e), 
                font=("Segoe UI", 9), 
                bg="#ffffff", 
                fg="#999999", 
                wraplength=500
            ).pack(pady=(0, 40))

        # Footer with close button
        footer_frame = Frame(recent_window, bg="#f5f7fa", height=70)
        footer_frame.pack(fill=X, side=BOTTOM)
        footer_frame.pack_propagate(False)
        
        close_btn = ttk.Button(
            footer_frame, 
            text="Close", 
            command=recent_window.destroy,
            width=15
        )
        close_btn.pack(pady=15)

    def menu_zoom_in(self) -> None:
        if not hasattr(self, "current_font_size"):
            self.current_font_size = 11
        self.current_font_size = min(self.current_font_size + 1, 16)
        messagebox.showinfo("Zoom", f"Font size increased to {self.current_font_size}pt.\n(Changes apply to new text widgets)")
        self.set_status(f"Zoom: {self.current_font_size}pt")

    def menu_zoom_out(self) -> None:
        if not hasattr(self, "current_font_size"):
            self.current_font_size = 11
        self.current_font_size = max(self.current_font_size - 1, 8)
        messagebox.showinfo("Zoom", f"Font size decreased to {self.current_font_size}pt.\n(Changes apply to new text widgets)")
        self.set_status(f"Zoom: {self.current_font_size}pt")

    def menu_reset_zoom(self) -> None:
        self.current_font_size = 11
        messagebox.showinfo("Zoom", "Font size reset to 11pt (default).\n(Changes apply to new text widgets)")
        self.set_status("Zoom: reset to default")

    def menu_fullscreen(self) -> None:
        current_state = self.root.attributes("-zoomed")
        self.root.attributes("-zoomed", not current_state)
        self.set_status("Fullscreen toggled" if not current_state else "Fullscreen disabled")

    def menu_batch_process(self) -> None:
        batch_window = Toplevel(self.root)
        batch_window.title("Batch Process Files")
        window_width = 600
        window_height = 500

        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()

        x = main_x + (main_width - window_width) // 2
        y = main_y + (main_height - window_height) // 2

        batch_window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        batch_window.transient(self.root)
        batch_window.grab_set()

        Label(batch_window, text="Batch Process Metadata Extraction", font=("Segoe UI", 14, "bold"), bg="#f5f7fa").pack(fill=X, padx=15, pady=10)

        main_frame = Frame(batch_window, bg="#ffffff")
        main_frame.pack(fill=BOTH, expand=True, padx=15, pady=10)

        Label(main_frame, text="Select files to process:", font=("Segoe UI", 10, "bold"), bg="#ffffff").pack(anchor=W, pady=(0, 8))

        files_listbox = Listbox(main_frame, height=10, bg="#ffffff", fg="#333333")
        files_listbox.pack(fill=BOTH, expand=True, pady=(0, 10))

        scrollbar = ttk.Scrollbar(files_listbox)
        scrollbar.pack(side=RIGHT, fill=Y)
        files_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=files_listbox.yview)

        def add_files():
            filetypes = (("All Files", "*.*"), ("Images", "*.jpg *.jpeg *.png *.gif *.bmp"), ("Documents", "*.pdf *.docx *.txt *.xlsx"))
            selected = filedialog.askopenfilenames(filetypes=filetypes)
            for file in selected:
                files_listbox.insert(END, file)

        def remove_file():
            selection = files_listbox.curselection()
            if selection:
                files_listbox.delete(selection[0])

        def clear_list():
            files_listbox.delete(0, END)

        def process_batch():
            file_list = files_listbox.get(0, END)
            if not file_list:
                messagebox.showwarning("No Files", "Please select files to process.")
                return

            try:
                processed = 0
                failed = 0
                batch_entries = []
                for path in file_list:
                    try:
                        if extractor:
                            metadata, _ = extractor.extract_and_store(path)
                            if isinstance(metadata, dict) and "Error" not in metadata:
                                processed += 1
                                batch_entries.append({"file_path": path, "metadata": metadata})
                            else:
                                failed += 1
                    except Exception:
                        failed += 1

                result_msg = f"Processed: {processed} files\nFailed: {failed} files"
                if risk_analyzer and batch_entries:
                    try:
                        self.risk_batch_summary = risk_analyzer.analyze_batch(batch_entries)
                        counts = self.risk_batch_summary.get("risk_counts", {})
                        result_msg += (
                            "\n\nRisk Summary:"
                            f"\nLOW: {counts.get('LOW', 0)}"
                            f"\nMEDIUM: {counts.get('MEDIUM', 0)}"
                            f"\nHIGH: {counts.get('HIGH', 0)}"
                        )
                    except Exception:
                        self.risk_batch_summary = None

                messagebox.showinfo("Batch Process Complete", result_msg)
                self._render_risk_analysis(self.risk_analysis)
                if callable(self.history_refresh):
                    self.history_refresh()
                batch_window.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Batch process failed: {str(e)}")

        button_frame = Frame(main_frame, bg="#ffffff")
        button_frame.pack(fill=X, pady=10)

        ttk.Button(button_frame, text="Add Files", command=add_files).pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Remove Selected", command=remove_file).pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Clear List", command=clear_list).pack(side=LEFT, padx=5)

        bottom_frame = Frame(batch_window, bg="#f5f7fa")
        bottom_frame.pack(fill=X, padx=15, pady=(10, 15))

        ttk.Button(bottom_frame, text="Process", command=process_batch).pack(side=RIGHT, padx=5)
        ttk.Button(bottom_frame, text="Cancel", command=batch_window.destroy).pack(side=RIGHT, padx=5)

    def _create_metric_card(self, parent, title, value, subtitle="", bg_start="#667eea", bg_end="#764ba2", width=None):
        """Create a material design-style card with gradient background for displaying metrics.
        
        Args:
            parent: Parent widget
            title: Card title/metric name
            value: Main value to display
            subtitle: Optional subtitle text
            bg_start: Gradient start color
            bg_end: Gradient end color
            width: Optional fixed width
            
        Returns:
            Frame: The created card frame
        """
        # Create card frame with shadow effect
        card_container = Frame(parent, bg="#e8e8e8", highlightthickness=0)
        
        # Inner card with gradient simulation (using a single color with white text)
        card = Frame(card_container, bg=bg_start, highlightthickness=0)
        card.pack(padx=3, pady=3, fill=BOTH, expand=True)
        
        # Add some padding
        content_frame = Frame(card, bg=bg_start)
        content_frame.pack(fill=BOTH, expand=True, padx=20, pady=18)
        
        # Title
        title_label = Label(content_frame, text=title, font=("Segoe UI", 10, "bold"), 
                           bg=bg_start, fg="white", anchor=W)
        title_label.pack(fill=X, pady=(0, 8))
        
        # Value
        value_label = Label(content_frame, text=value, font=("Segoe UI", 24, "bold"), 
                           bg=bg_start, fg="white", anchor=W)
        value_label.pack(fill=X, pady=(0, 5))
        
        # Subtitle
        if subtitle:
            subtitle_label = Label(content_frame, text=subtitle, font=("Segoe UI", 9), 
                                  bg=bg_start, fg="#f0f0f0", anchor=W)
            subtitle_label.pack(fill=X)
        
        # Hover effect
        def on_enter(e):
            card.config(bg=bg_end)
            content_frame.config(bg=bg_end)
            title_label.config(bg=bg_end)
            value_label.config(bg=bg_end)
            if subtitle:
                subtitle_label.config(bg=bg_end)
        
        def on_leave(e):
            card.config(bg=bg_start)
            content_frame.config(bg=bg_start)
            title_label.config(bg=bg_start)
            value_label.config(bg=bg_start)
            if subtitle:
                subtitle_label.config(bg=bg_start)
        
        card_container.bind("<Enter>", on_enter)
        card_container.bind("<Leave>", on_leave)
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)
        content_frame.bind("<Enter>", on_enter)
        content_frame.bind("<Leave>", on_leave)
        title_label.bind("<Enter>", on_enter)
        title_label.bind("<Leave>", on_leave)
        value_label.bind("<Enter>", on_enter)
        value_label.bind("<Leave>", on_leave)
        if subtitle:
            subtitle_label.bind("<Enter>", on_enter)
            subtitle_label.bind("<Leave>", on_leave)
        
        return card_container

    def menu_statistics(self) -> None:
        """Display enhanced statistics dashboard with material design cards and interactive charts."""
        stats_window = Toplevel(self.root)
        stats_window.title("Statistics Dashboard")
        stats_window.config(bg="#f0f2f5")
        
        # Responsive window sizing (0.75 of screen size for better visibility)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_w = int(screen_width * 0.75)
        window_h = int(screen_height * 0.75)
        x = (screen_width - window_w) // 2
        y = (screen_height - window_h) // 2
        stats_window.geometry(f"{window_w}x{window_h}+{x}+{y}")
        stats_window.minsize(800, 600)  # Set minimum size
        
        stats_window.transient(self.root)
        stats_window.grab_set()

        # State variables for filters
        filter_vars = {
            'date_range': StringVar(value="All Time"),
            'file_type': StringVar(value="All Types"),
            'search': StringVar(value=""),
            'auto_refresh': BooleanVar(value=False)
        }
        dashboard_state = {
            'refresh_after_id': None,
            'request_token': 0,
            'records_cache': None,
            'risk_cache': {},
        }

        # Modern gradient header with controls
        header_frame = Frame(stats_window, bg="#667eea", height=90)
        header_frame.pack(fill=X)
        header_frame.pack_propagate(False)
        
        header_content = Frame(header_frame, bg="#667eea")
        header_content.pack(fill=BOTH, expand=True, padx=20, pady=10)
        
        Label(header_content, text="Statistical Dashboard", 
              font=("Segoe UI", 20, "bold"), bg="#667eea", fg="white").pack(side=LEFT)
        
        # Refresh button
        refresh_btn = Button(header_content, text="⟳ Refresh", 
                            command=lambda: schedule_refresh(force_fetch=True),
                            bg="#5a67d8", fg="white", font=("Segoe UI", 10, "bold"),
                            relief=FLAT, cursor="hand2", padx=15, pady=8)
        refresh_btn.pack(side=RIGHT, padx=5)
        
        # Auto-refresh toggle
        auto_check = ttk.Checkbutton(header_content, text="Auto-refresh", 
                                     variable=filter_vars['auto_refresh'],
                                     command=lambda: toggle_auto_refresh())
        auto_check.pack(side=RIGHT, padx=10)

        # Filter bar - maximize width usage
        filter_frame = Frame(stats_window, bg="white", height=60)
        filter_frame.pack(fill=X, padx=10, pady=(10, 0))
        filter_frame.pack_propagate(False)
        
        filter_content = Frame(filter_frame, bg="white")
        filter_content.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # Date range filter
        Label(filter_content, text="Period:", font=("Segoe UI", 10, "bold"),
              bg="white").pack(side=LEFT, padx=(0, 5))
        date_combo = ttk.Combobox(filter_content, textvariable=filter_vars['date_range'],
                                  values=["All Time", "Last 7 Days", "Last 30 Days", 
                                         "Last 90 Days", "This Year"],
                                  state="readonly", width=15)
        date_combo.pack(side=LEFT, padx=5)
        date_combo.bind('<<ComboboxSelected>>', lambda e: schedule_refresh())
        
        # File type filter
        Label(filter_content, text="Type:", font=("Segoe UI", 10, "bold"),
              bg="white").pack(side=LEFT, padx=(20, 5))
        type_combo = ttk.Combobox(filter_content, textvariable=filter_vars['file_type'],
                                  state="readonly", width=15)
        type_combo.pack(side=LEFT, padx=5)
        type_combo.bind('<<ComboboxSelected>>', lambda e: schedule_refresh())
        
        # Search box
        Label(filter_content, text="Search:", font=("Segoe UI", 10, "bold"),
              bg="white").pack(side=LEFT, padx=(20, 5))
        search_entry = ttk.Entry(filter_content, textvariable=filter_vars['search'], width=25)
        search_entry.pack(side=LEFT, padx=5)
        search_entry.bind('<KeyRelease>', lambda e: schedule_refresh(delay_ms=350))
        
        # Apply filters button
        apply_btn = Button(filter_content, text="Apply Filters",
                          command=lambda: schedule_refresh(),
                          bg="#667eea", fg="white", font=("Segoe UI", 9, "bold"),
                          relief=FLAT, cursor="hand2", padx=12, pady=5)
        apply_btn.pack(side=RIGHT, padx=5)

        # Create main container with scrollbar (hidden)
        container = Frame(stats_window, bg="#f0f2f5")
        container.pack(fill=BOTH, expand=True, padx=0, pady=0)

        # Create canvas without visible scrollbar
        canvas = Canvas(container, bg="#f0f2f5", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = Frame(canvas, bg="#f0f2f5")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Update scrollable frame width to match canvas width
        def update_frame_width(event=None):
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
        
        canvas.bind('<Configure>', update_frame_width)

        # Pack canvas with full width and visible vertical scrollbar
        canvas.pack(side=LEFT, fill=BOTH, expand=True, padx=0)
        scrollbar.pack(side=RIGHT, fill=Y)

        # Enable mouse wheel scrolling
        def on_mousewheel(event):
            try:
                if not canvas.winfo_exists():
                    return

                delta_steps = 0
                if hasattr(event, "delta") and event.delta:
                    delta_steps = int(-1 * (event.delta / 120))
                elif getattr(event, "num", None) == 4:
                    delta_steps = -1
                elif getattr(event, "num", None) == 5:
                    delta_steps = 1

                if delta_steps:
                    canvas.yview_scroll(delta_steps, "units")
            except Exception:
                pass

        stats_window.bind("<MouseWheel>", on_mousewheel, add="+")
        stats_window.bind("<Button-4>", on_mousewheel, add="+")
        stats_window.bind("<Button-5>", on_mousewheel, add="+")

        def close_stats_window():
            if stats_window.winfo_exists():
                stats_window.destroy()
        stats_window.protocol("WM_DELETE_WINDOW", close_stats_window)

        # Helper functions for filtering and calculations
        def parse_size_to_bytes(size_str):
            """Convert formatted size string to bytes."""
            if not size_str or size_str == "Unknown":
                return 0
            try:
                parts = str(size_str).strip().split()
                if len(parts) == 2:
                    value = float(parts[0])
                    unit = parts[1].upper()
                    multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
                    return int(value * multipliers.get(unit, 1))
                return int(float(size_str))
            except (ValueError, IndexError, AttributeError):
                return 0

        def format_size(bytes_val):
            """Format bytes to human-readable size."""
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if bytes_val < 1024.0 or unit == 'TB':
                    return f"{bytes_val:.1f} {unit}"
                bytes_val /= 1024.0
            return f"{bytes_val:.1f} TB"

        def filter_records(records, criteria):
            """Apply filters to records."""
            filtered = list(records)
            
            # Date filter
            date_range = criteria.get('date_range', 'All Time')
            if date_range != "All Time":
                now = datetime.now()
                if date_range == "Last 7 Days":
                    cutoff = now - timedelta(days=7)
                elif date_range == "Last 30 Days":
                    cutoff = now - timedelta(days=30)
                elif date_range == "Last 90 Days":
                    cutoff = now - timedelta(days=90)
                elif date_range == "This Year":
                    cutoff = datetime(now.year, 1, 1)
                else:
                    cutoff = datetime.min
                
                date_filtered = []
                for record in filtered:
                    if len(record) <= 5 or not record[5]:
                        continue
                    try:
                        if datetime.fromisoformat(record[5]) >= cutoff:
                            date_filtered.append(record)
                    except Exception:
                        continue
                filtered = date_filtered
            
            # File type filter
            file_type = criteria.get('file_type', 'All Types')
            if file_type != "All Types":
                filtered = [r for r in filtered if len(r) > 4 and r[4] == file_type]
            
            # Search filter
            search_term = criteria.get('search', '').lower()
            if search_term:
                filtered = [r for r in filtered if len(r) > 2 and 
                           search_term in r[2].lower()]
            
            return filtered

        def calculate_enhanced_stats(records):
            """Calculate enhanced statistics."""
            total = len(records)
            if total == 0:
                return None
            
            stats = {
                'total': total,
                'file_types': {},
                'total_size': 0,
                'file_sizes': [],
                'sizes_by_type': defaultdict(list),
                'dates': [],
                'files_by_date': defaultdict(int),
                'risk_counts': {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0}
            }
            
            for record in records:
                ft = record[4] if len(record) > 4 else "Unknown"
                stats['file_types'][ft] = stats['file_types'].get(ft, 0) + 1
                
                size_bytes = parse_size_to_bytes(record[3]) if len(record) > 3 else 0
                stats['total_size'] += size_bytes
                stats['file_sizes'].append((size_bytes, record[2] if len(record) > 2 else "Unknown"))
                stats['sizes_by_type'][ft].append(size_bytes)
                
                if len(record) > 5 and record[5]:
                    try:
                        date_obj = datetime.fromisoformat(record[5])
                        date_key = date_obj.strftime('%Y-%m-%d')
                        stats['dates'].append(date_obj)
                        stats['files_by_date'][date_key] += 1
                    except Exception:
                        pass

                if risk_analyzer and len(record) > 7 and record[7]:
                    try:
                        cache_key = (
                            record[0] if len(record) > 0 else None,
                            record[5] if len(record) > 5 else None,
                            record[6] if len(record) > 6 else None,
                        )
                        risk_level = dashboard_state['risk_cache'].get(cache_key)
                        if risk_level is None:
                            parsed_metadata = json.loads(record[7]) if isinstance(record[7], str) else (record[7] or {})
                            record_path = record[1] if len(record) > 1 else ""
                            risk_result = risk_analyzer.analyze_metadata(
                                parsed_metadata,
                                record_path,
                                fallback_timestamps={
                                    "Created Date": datetime.fromtimestamp(os.path.getctime(record_path)).isoformat(sep=" ", timespec="seconds") if record_path and os.path.exists(record_path) else None,
                                    "Modified Date": record[6] if len(record) > 6 else None,
                                    "Extraction Date": record[5] if len(record) > 5 else None,
                                },
                            )
                            risk_level = risk_result.get('risk_level', 'LOW')
                            dashboard_state['risk_cache'][cache_key] = risk_level
                        stats['risk_counts'][risk_level] = stats['risk_counts'].get(risk_level, 0) + 1
                    except Exception:
                        pass
            
            stats['avg_size'] = stats['total_size'] / total if total > 0 else 0
            stats['max_size'] = max(stats['file_sizes'], key=lambda x: x[0]) if stats['file_sizes'] else (0, "Unknown")
            stats['min_size'] = min([f for f in stats['file_sizes'] if f[0] > 0], key=lambda x: x[0]) if stats['file_sizes'] else (0, "Unknown")
            stats['largest_files'] = sorted(stats['file_sizes'], key=lambda x: x[0], reverse=True)[:10]
            stats['avg_size_by_type'] = {
                ft: sum(sizes)/len(sizes) if sizes else 0 
                for ft, sizes in stats['sizes_by_type'].items()
            }
            
            return stats

        def _cancel_pending_refresh():
            pending = dashboard_state.get('refresh_after_id')
            if pending is not None:
                try:
                    stats_window.after_cancel(pending)
                except Exception:
                    pass
                dashboard_state['refresh_after_id'] = None

        def schedule_refresh(delay_ms=0, force_fetch=False):
            """Schedule a dashboard refresh, debounced for frequent filter events."""
            _cancel_pending_refresh()
            if delay_ms and delay_ms > 0:
                dashboard_state['refresh_after_id'] = stats_window.after(delay_ms, lambda: refresh_dashboard(force_fetch=force_fetch))
            else:
                refresh_dashboard(force_fetch=force_fetch)

        def refresh_dashboard(force_fetch=False):
            """Refresh dashboard with current filters without blocking the UI."""
            _cancel_pending_refresh()
            if not stats_window.winfo_exists():
                return

            dashboard_state['request_token'] += 1
            request_token = dashboard_state['request_token']
            criteria = {
                'date_range': filter_vars['date_range'].get(),
                'file_type': filter_vars['file_type'].get(),
                'search': filter_vars['search'].get(),
            }

            for widget in scrollable_frame.winfo_children():
                widget.destroy()
            loading_frame = Frame(scrollable_frame, bg="white", relief=FLAT)
            loading_frame.pack(fill=BOTH, expand=True, padx=20, pady=50)
            Label(loading_frame, text="Loading statistics...",
                  font=("Segoe UI", 14, "bold"), bg="white", fg="#667eea").pack(pady=(30, 10))

            refresh_btn.config(state=DISABLED, text="Refreshing...")

            def worker():
                try:
                    use_cached = dashboard_state['records_cache'] is not None and not force_fetch
                    all_records = dashboard_state['records_cache'] if use_cached else db.fetch_all_metadata()
                    all_types = sorted({r[4] for r in all_records if len(r) > 4})
                    filtered = filter_records(all_records, criteria)
                    stats = calculate_enhanced_stats(filtered)
                    payload = (all_records, all_types, filtered, stats, None)
                except Exception as err:
                    payload = (None, None, None, None, err)

                def apply_result():
                    if not stats_window.winfo_exists():
                        return
                    if request_token != dashboard_state['request_token']:
                        return

                    refresh_btn.config(state=NORMAL, text="⟳ Refresh")
                    for widget in scrollable_frame.winfo_children():
                        widget.destroy()

                    all_records, all_types, filtered, stats, error = payload
                    if error is not None:
                        error_frame = Frame(scrollable_frame, bg="white", relief=FLAT)
                        error_frame.pack(fill=BOTH, expand=True, padx=20, pady=50)
                        Label(error_frame, text="Error Loading Statistics",
                              font=("Segoe UI", 16, "bold"), bg="white", fg="#e74c3c").pack(pady=(30, 10))
                        Label(error_frame, text=str(error),
                              font=("Segoe UI", 11), bg="white", fg="#95a5a6").pack(pady=(0, 30))
                        return

                    dashboard_state['records_cache'] = all_records
                    type_combo['values'] = ["All Types"] + all_types

                    if stats is None or stats['total'] == 0:
                        empty_frame = Frame(scrollable_frame, bg="white", relief=FLAT)
                        empty_frame.pack(fill=BOTH, expand=True, padx=20, pady=50)
                        Label(empty_frame, text="No matching data",
                              font=("Segoe UI", 16, "bold"), bg="white", fg="#888").pack(pady=(30, 10))
                        Label(empty_frame, text="Adjust filters or extract more files!",
                              font=("Segoe UI", 12), bg="white", fg="#aaa").pack(pady=(0, 30))
                        return

                    render_enhanced_dashboard(stats, filtered)

                stats_window.after(0, apply_result)

            threading.Thread(target=worker, daemon=True).start()

        def toggle_auto_refresh():
            """Toggle auto-refresh functionality."""
            if filter_vars['auto_refresh'].get():
                def auto_update():
                    if filter_vars['auto_refresh'].get():
                        schedule_refresh(force_fetch=True)
                        stats_window.after(30000, auto_update)
                stats_window.after(30000, auto_update)

        def render_enhanced_dashboard(stats, filtered_records):
            """Render enhanced dashboard with all features."""
            gradient_colors = ['#667eea', '#764ba2', '#f093fb', '#4facfe',
                             '#43e97b', '#fa709a', '#fee140', '#30cfd0']

            # Enhanced metrics cards row 1 - maximize space usage
            cards_container1 = Frame(scrollable_frame, bg="#f0f2f5")
            cards_container1.pack(fill=X, padx=10, pady=(10, 8))
            cards_row1 = Frame(cards_container1, bg="#f0f2f5")
            cards_row1.pack(fill=X)

            self._create_metric_card(cards_row1, "Total Files", str(stats['total']),
                                    "Analyzed", "#667eea", "#764ba2").pack(side=LEFT, fill=BOTH, expand=True, padx=3)
            self._create_metric_card(cards_row1, "Total Size", format_size(stats['total_size']),
                                    "Storage", "#4facfe", "#00f2fe").pack(side=LEFT, fill=BOTH, expand=True, padx=3)
            self._create_metric_card(cards_row1, "File Types", str(len(stats['file_types'])),
                                    "Formats", "#43e97b", "#38f9d7").pack(side=LEFT, fill=BOTH, expand=True, padx=3)
            self._create_metric_card(cards_row1, "Average Size", format_size(stats['avg_size']),
                                    "Per File", "#fa709a", "#fee140").pack(side=LEFT, fill=BOTH, expand=True, padx=3)

            # Enhanced metrics cards row 2 - maximize space usage
            cards_container2 = Frame(scrollable_frame, bg="#f0f2f5")
            cards_container2.pack(fill=X, padx=10, pady=8)
            cards_row2 = Frame(cards_container2, bg="#f0f2f5")
            cards_row2.pack(fill=X)

            largest_name = stats['max_size'][1][:20] + "..." if len(stats['max_size'][1]) > 20 else stats['max_size'][1]
            self._create_metric_card(cards_row2, "Largest File", format_size(stats['max_size'][0]),
                                    largest_name, "#f093fb", "#4facfe").pack(side=LEFT, fill=BOTH, expand=True, padx=3)
            
            smallest_name = stats['min_size'][1][:20] + "..." if len(stats['min_size'][1]) > 20 else stats['min_size'][1]
            self._create_metric_card(cards_row2, "Smallest File", format_size(stats['min_size'][0]),
                                    smallest_name, "#764ba2", "#667eea").pack(side=LEFT, fill=BOTH, expand=True, padx=3)
            
            avg_per_day = stats['total'] / max(len(stats['files_by_date']), 1)
            self._create_metric_card(cards_row2, "Daily Average", f"{avg_per_day:.1f}",
                                    "Files/Day", "#30cfd0", "#667eea").pack(side=LEFT, fill=BOTH, expand=True, padx=3)
            
            most_common_type = max(stats['file_types'].items(), key=lambda x: x[1]) if stats['file_types'] else ("N/A", 0)
            self._create_metric_card(cards_row2, "Top Format", most_common_type[0],
                                    f"{most_common_type[1]} files", "#fa709a", "#764ba2").pack(side=LEFT, fill=BOTH, expand=True, padx=3)

            # Risk metrics row
            cards_container3 = Frame(scrollable_frame, bg="#f0f2f5")
            cards_container3.pack(fill=X, padx=10, pady=8)
            cards_row3 = Frame(cards_container3, bg="#f0f2f5")
            cards_row3.pack(fill=X)

            self._create_metric_card(cards_row3, "High Risk Files", str(stats['risk_counts'].get('HIGH', 0)),
                                    "Privacy alerts", "#e74c3c", "#c0392b").pack(side=LEFT, fill=BOTH, expand=True, padx=3)
            self._create_metric_card(cards_row3, "Medium Risk Files", str(stats['risk_counts'].get('MEDIUM', 0)),
                                    "Needs review", "#f39c12", "#d35400").pack(side=LEFT, fill=BOTH, expand=True, padx=3)
            self._create_metric_card(cards_row3, "Low Risk Files", str(stats['risk_counts'].get('LOW', 0)),
                                    "Safer metadata", "#27ae60", "#16a085").pack(side=LEFT, fill=BOTH, expand=True, padx=3)

            # Additional charts section - maximize space usage
            charts_section1 = Frame(scrollable_frame, bg="#f0f2f5")
            charts_section1.pack(fill=BOTH, expand=True, padx=10, pady=(8, 0))
            
            Label(charts_section1, text="Extended Analytics", 
                  font=("Segoe UI", 14, "bold"), bg="#f0f2f5", fg="#2c3e50").pack(anchor=W, pady=(0, 10))
            
            charts_frame1 = Frame(charts_section1, bg="white", relief=FLAT, bd=2)
            charts_frame1.pack(fill=BOTH, expand=True)

            # Create enhanced charts with better width utilization
            fig1_width = max((window_w - 80) / 100, 12)
            fig1 = Figure(figsize=(fig1_width, 5), facecolor='white')
            
            # Line chart for trends over time
            ax1 = fig1.add_subplot(131)
            if stats['files_by_date']:
                sorted_dates = sorted(stats['files_by_date'].items())
                dates = [datetime.strptime(d, '%Y-%m-%d') for d, _ in sorted_dates]
                counts = [c for _, c in sorted_dates]
                ax1.plot(dates, counts, color='#667eea', linewidth=2, marker='o', markersize=4)
                ax1.fill_between(dates, counts, alpha=0.3, color='#667eea')
                ax1.set_xlabel('Date', fontsize=9)
                ax1.set_ylabel('Files', fontsize=9)
                ax1.set_title('Trends Over Time', fontsize=10, weight='bold', pad=10)
                ax1.grid(axis='y', alpha=0.2)
                plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right', fontsize=8)
            
            # Histogram for file size distribution
            ax2 = fig1.add_subplot(132)
            sizes_only = [s[0] for s in stats['file_sizes'] if s[0] > 0]
            if sizes_only:
                ax2.hist(sizes_only, bins=15, color='#43e97b', edgecolor='white', alpha=0.85)
                ax2.set_xlabel('File Size (bytes)', fontsize=9)
                ax2.set_ylabel('Count', fontsize=9)
                ax2.set_title('Size Distribution', fontsize=10, weight='bold', pad=10)
                ax2.grid(axis='y', alpha=0.2)
            
            # Top 5 files as horizontal bars
            ax3 = fig1.add_subplot(133)
            if stats['largest_files']:
                top5 = stats['largest_files'][:5]
                names = [f[:20] + "..." if len(f) > 20 else f for _, f in top5]
                sizes = [s for s, _ in top5]
                y_pos = range(len(names))
                ax3.barh(y_pos, sizes, color=gradient_colors[:len(names)], edgecolor='white', alpha=0.85)
                ax3.set_yticks(y_pos)
                ax3.set_yticklabels(names, fontsize=8)
                ax3.set_xlabel('Size (bytes)', fontsize=9)
                ax3.set_title('Top 5 Largest Files', fontsize=10, weight='bold', pad=10)
                ax3.invert_yaxis()
            
            fig1.tight_layout(pad=2)
            chart_canvas1 = FigureCanvasTkAgg(fig1, master=charts_frame1)
            chart_canvas1.draw()
            chart_canvas1.get_tk_widget().pack(fill=BOTH, expand=True, padx=10, pady=10)
            plt.close(fig1)

            # Metadata Insights - maximize space usage
            insights_section = Frame(scrollable_frame, bg="#f0f2f5")
            insights_section.pack(fill=X, padx=10, pady=(15, 0))
            
            Label(insights_section, text="Metadata Insights", 
                  font=("Segoe UI", 14, "bold"), bg="#f0f2f5", fg="#2c3e50").pack(anchor=W, pady=(0, 10))
            
            insights_frame = Frame(insights_section, bg="white", relief=FLAT, bd=2)
            insights_frame.pack(fill=X, padx=0, pady=0)
            
            insights_grid = Frame(insights_frame, bg="white")
            insights_grid.pack(fill=X, padx=20, pady=15)
            
            # Duplicate detection
            filenames = [r[2] for r in filtered_records if len(r) > 2]
            filename_counts = Counter(filenames)
            duplicates = {name: count for name, count in filename_counts.items() if count > 1}
            
            Label(insights_grid, text=f"Potential Duplicates: {len(duplicates)}", 
                  font=("Segoe UI", 11, "bold"), bg="white", 
                  fg="#e74c3c" if duplicates else "#27ae60").grid(row=0, column=0, sticky=W, padx=10, pady=5)
            Label(insights_grid, text=f"Unique Files: {len(filename_counts)}", 
                  font=("Segoe UI", 11), bg="white", fg="#2c3e50").grid(row=0, column=1, sticky=W, padx=10, pady=5)
            
            # Completeness score
            complete_count = sum(1 for r in filtered_records if len(r) >= 6 and all(r[i] for i in range(2, 6)))
            completeness = (complete_count / stats['total'] * 100) if stats['total'] > 0 else 0
            Label(insights_grid, text=f"Metadata Completeness: {completeness:.1f}%", 
                  font=("Segoe UI", 11, "bold"), bg="white", 
                  fg="#27ae60" if completeness > 80 else "#f39c12").grid(row=0, column=2, sticky=W, padx=10, pady=5)

            # Recent extractions with enhanced info - maximize space usage
            recent_section = Frame(scrollable_frame, bg="#f0f2f5")
            recent_section.pack(fill=X, padx=10, pady=(15, 15))
            
            Label(recent_section, text="Recent Extractions", 
                  font=("Segoe UI", 14, "bold"), bg="#f0f2f5", fg="#2c3e50").pack(anchor=W, pady=(0, 10))
            
            recent_frame = Frame(recent_section, bg="white", relief=FLAT, bd=2)
            recent_frame.pack(fill=X)
            
            recent = sorted(filtered_records, key=lambda x: x[5] if len(x) > 5 else "", reverse=True)[:5]
            for i, record in enumerate(recent, 1):
                filename = record[2] if len(record) > 2 else "Unknown"
                file_type = record[4] if len(record) > 4 else "Unknown"
                file_size = record[3] if len(record) > 3 else "0 B"
                display_name = filename[:60] + '...' if len(filename) > 60 else filename
                
                row_frame = Frame(recent_frame, bg="white", cursor="hand2")
                row_frame.pack(fill=X, padx=15, pady=8)
                
                badge = Label(row_frame, text=str(i), font=("Segoe UI", 10, "bold"),
                            bg=gradient_colors[i-1], fg="white", width=3, height=1)
                badge.pack(side=LEFT, padx=(0, 12))
                
                info_frame = Frame(row_frame, bg="white")
                info_frame.pack(side=LEFT, fill=X, expand=True)
                
                Label(info_frame, text=display_name, font=("Segoe UI", 10, "bold"),
                     bg="white", fg="#2c3e50", anchor=W).pack(fill=X)
                Label(info_frame, text=f"{file_type} • {file_size}", font=("Segoe UI", 9),
                     bg="white", fg="#7f8c8d", anchor=W).pack(fill=X)
                
                def make_hover(frame, bg_color, badge_widget):
                    def on_enter(e):
                        frame.config(bg=bg_color)
                        for child in frame.winfo_children():
                            if child == badge_widget:
                                continue
                            if isinstance(child, (Label, Frame)):
                                child.config(bg=bg_color)
                            if isinstance(child, Frame):
                                for subchild in child.winfo_children():
                                    if isinstance(subchild, Label):
                                        subchild.config(bg=bg_color)
                    
                    def on_leave(e):
                        frame.config(bg="white")
                        for child in frame.winfo_children():
                            if child == badge_widget:
                                continue
                            if isinstance(child, (Label, Frame)):
                                child.config(bg="white")
                            if isinstance(child, Frame):
                                for subchild in child.winfo_children():
                                    if isinstance(subchild, Label):
                                        subchild.config(bg="white")
                    
                    return on_enter, on_leave
                
                enter, leave = make_hover(row_frame, "#f8f9fa", badge)
                row_frame.bind("<Enter>", enter)
                row_frame.bind("<Leave>", leave)

        # Initial load
        schedule_refresh(force_fetch=True)

        # Close button
        button_frame = Frame(stats_window, bg="#f0f2f5", height=60)
        button_frame.pack(fill=X, side=BOTTOM)
        button_frame.pack_propagate(False)
        
        close_btn = Button(button_frame, text="Close Dashboard",
                          command=close_stats_window,
                          bg="#667eea", fg="white", font=("Segoe UI", 11, "bold"),
                          relief=FLAT, cursor="hand2", padx=30, pady=10,
                          activebackground="#764ba2", activeforeground="white")
        close_btn.pack(pady=10)
        
        def on_btn_enter(e):
            close_btn.config(bg="#764ba2")
        def on_btn_leave(e):
            close_btn.config(bg="#667eea")
        
        close_btn.bind("<Enter>", on_btn_enter)
        close_btn.bind("<Leave>", on_btn_leave)

    def menu_check_updates(self) -> None:
        messagebox.showinfo(
            "Check for Updates",
            "You are using TraceLens v1.0\n\nAlready up to date!\n\nFor the latest version, visit the project repository.",
        )

    def menu_credits(self) -> None:
        credits_text = (
            "TraceLens\n\n"
            "Development Team:\n"
            "  • Tanmay Bhatnagar\n"
        )
        messagebox.showinfo("Credits", credits_text)

    def menu_report_issue(self) -> None:
        issue_window = Toplevel(self.root)
        issue_window.title("Report an Issue")
        issue_window.geometry("600x500")
        issue_window.transient(self.root)
        issue_window.grab_set()
        issue_window.update_idletasks()
        parent_x = self.root.winfo_rootx()
        parent_y = self.root.winfo_rooty()
        parent_w = self.root.winfo_width()
        parent_h = self.root.winfo_height()
        win_w = issue_window.winfo_width()
        win_h = issue_window.winfo_height()
        center_x = parent_x + (parent_w - win_w) // 2
        center_y = parent_y + (parent_h - win_h) // 2
        issue_window.geometry(f"{win_w}x{win_h}+{center_x}+{center_y}")

        Label(issue_window, text="Report an Issue", font=("Segoe UI", 14, "bold"), bg="#f5f7fa").pack(fill=X, padx=15, pady=10)

        main_frame = Frame(issue_window, bg="#ffffff")
        main_frame.pack(fill=BOTH, expand=True, padx=15, pady=10)

        Label(main_frame, text="Issue Title:", font=("Segoe UI", 10, "bold"), bg="#ffffff").pack(anchor=W, pady=(0, 5))
        title_entry = ttk.Entry(main_frame, width=50)
        title_entry.pack(fill=X, pady=(0, 10))

        Label(main_frame, text="Description:", font=("Segoe UI", 10, "bold"), bg="#ffffff").pack(anchor=W, pady=(0, 5))
        desc_text = scrolledtext.ScrolledText(main_frame, height=12, width=60, wrap=WORD, font=("Segoe UI", 10))
        desc_text.pack(fill=BOTH, expand=True, pady=(0, 10))

        Label(main_frame, text="Category:", font=("Segoe UI", 10, "bold"), bg="#ffffff").pack(anchor=W, pady=(0, 5))
        category_var = StringVar()
        ttk.Combobox(main_frame, textvariable=category_var, values=["Bug", "Feature Request", "Improvement", "Documentation", "Other"], state="readonly", width=47).pack(fill=X, pady=(0, 10))

        def submit_issue():
            if not title_entry.get():
                messagebox.showwarning("Missing Info", "Please enter an issue title.")
                return
            messagebox.showinfo("Thank You", "Your issue has been submitted.\n\nWe appreciate your feedback!")
            issue_window.destroy()

        button_frame = Frame(issue_window, bg="#f5f7fa")
        button_frame.pack(fill=X, padx=15, pady=(10, 15))

        ttk.Button(button_frame, text="Submit", command=submit_issue).pack(side=RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=issue_window.destroy).pack(side=RIGHT, padx=5)

    def menu_contact_support(self) -> None:
        support_text = (
            "Contact Support\n\n"
            "Email: tanmaybhatnagar760@gmail.com\n"
            "GitHub: https://github.com/Tanmay-Bhatnagar22/Metadata-Analyzer\n\n"
            "Response Time: 24-48 hours\n\n"
            "For urgent issues, please use the\n"
            "'Report an Issue' feature or visit\n"
            "our GitHub repository."
        )
        messagebox.showinfo("Contact Support", support_text)

    # ------------------------------------------------------------------
    # Keyboard shortcuts setup
    # ------------------------------------------------------------------
    def _setup_keyboard_shortcuts(self) -> None:
        """Bind keyboard shortcuts to their respective commands.
        
        Sets up all keyboard shortcuts shown in menu accelerators.
        """
        # File menu shortcuts
        self.root.bind('<Control-n>', lambda e: self.menu_new_project())
        self.root.bind('<Control-N>', lambda e: self.menu_new_project())
        self.root.bind('<Control-o>', lambda e: self.choose_file())
        self.root.bind('<Control-O>', lambda e: self.choose_file())
        self.root.bind('<Control-e>', lambda e: self.menu_export_results())
        self.root.bind('<Control-E>', lambda e: self.menu_export_results())
        
        # Edit menu shortcuts
        self.root.bind('<Control-c>', lambda e: self.menu_copy_results())
        self.root.bind('<Control-C>', lambda e: self.menu_copy_results())
        
        # View menu shortcuts
        self.root.bind('<F5>', lambda e: self.menu_refresh_all())
        self.root.bind('<Control-plus>', lambda e: self.menu_zoom_in())
        self.root.bind('<Control-equal>', lambda e: self.menu_zoom_in())  # Handle + key without shift
        self.root.bind('<Control-minus>', lambda e: self.menu_zoom_out())
        self.root.bind('<Control-0>', lambda e: self.menu_reset_zoom())
        self.root.bind('<F11>', lambda e: self.menu_fullscreen())
        
        # Help menu shortcuts
        self.root.bind('<F1>', lambda e: self.menu_show_documentation())
        self.root.bind('<Control-question>', lambda e: self.menu_show_shortcuts())
        self.root.bind('<Control-slash>', lambda e: self.menu_show_shortcuts())  # Alternative for Ctrl+?

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------
    def _build_menu_bar(self) -> None:
        """Build application menu bar with File, Edit, View, and Help menus.
        
        Creates menu items for file operations, editing, viewing options, and help/support.
        """
        menu = Menu(self.root, bg="#f5f7fa", fg="#1a1a1a", activebackground="#0066cc", activeforeground="#ffffff", relief=FLAT, bd=0)
        self.root.config(menu=menu)

        file_menu = Menu(menu, tearoff=0, bg="#f5f7fa", fg="#1a1a1a", activebackground="#0066cc", activeforeground="#ffffff")
        menu.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Project", command=self.menu_new_project, accelerator="Ctrl+N")
        file_menu.add_command(label="Open File", command=self.choose_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Import Metadata", command=self.menu_import_metadata)
        file_menu.add_command(label="Export Results", command=self.menu_export_results, accelerator="Ctrl+E")
        file_menu.add_separator()
        file_menu.add_command(label="Recent Files", command=self.menu_recent_files)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit, accelerator="Alt+F4")

        edit_menu = Menu(menu, tearoff=0, bg="#f5f7fa", fg="#1a1a1a", activebackground="#0066cc", activeforeground="#ffffff")
        menu.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Clear All Data", command=self.menu_clear_all_data)
        edit_menu.add_command(label="Copy Results", command=self.menu_copy_results, accelerator="Ctrl+C")

        view_menu = Menu(menu, tearoff=0, bg="#f5f7fa", fg="#1a1a1a", activebackground="#0066cc", activeforeground="#ffffff")
        menu.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Refresh All Data", command=self.menu_refresh_all, accelerator="F5")
        view_menu.add_separator()
        view_menu.add_command(label="Zoom In", command=self.menu_zoom_in, accelerator="Ctrl++")
        view_menu.add_command(label="Zoom Out", command=self.menu_zoom_out, accelerator="Ctrl+-")
        view_menu.add_command(label="Reset Zoom", command=self.menu_reset_zoom, accelerator="Ctrl+0")
        view_menu.add_separator()
        view_menu.add_command(label="Full Screen", command=self.menu_fullscreen, accelerator="F11")

        tools_menu = Menu(menu, tearoff=0, bg="#f5f7fa", fg="#1a1a1a", activebackground="#0066cc", activeforeground="#ffffff")
        menu.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Generate Report", command=self.generate_report)
        tools_menu.add_command(label="Batch Process", command=self.menu_batch_process)
        tools_menu.add_separator()
        tools_menu.add_command(label="Backup Database", command=self.menu_backup_database)
        tools_menu.add_command(label="Clear History", command=self.menu_clear_history)
        tools_menu.add_separator()
        tools_menu.add_command(label="Statistics Dashboard", command=self.menu_statistics)

        help_menu = Menu(menu, tearoff=0, bg="#f5f7fa", fg="#1a1a1a", activebackground="#0066cc", activeforeground="#ffffff")
        menu.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Documentation", command=self.menu_show_documentation, accelerator="F1")
        help_menu.add_command(label="Getting Started", command=self.menu_show_documentation)
        help_menu.add_command(label="Keyboard Shortcuts", command=self.menu_show_shortcuts, accelerator="Ctrl+?")
        help_menu.add_separator()
        help_menu.add_command(label="Check for Updates", command=self.menu_check_updates)
        help_menu.add_separator()
        help_menu.add_command(label="About TraceLens", command=self.menu_show_about)
        help_menu.add_command(label="Credits", command=self.menu_credits)
        help_menu.add_command(label="Report an Issue", command=self.menu_report_issue)
        help_menu.add_command(label="Contact Support", command=self.menu_contact_support)


# Public entrypoint to maintain existing API


def run_gui() -> None:
    app = MetadataAnalyzerApp()
    app.run()
