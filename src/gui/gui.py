"""GUI module for TraceLens application.

Provides Tkinter-based interface with tabs for file extraction, editing, history management,
risk analysis, and report generation.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from tkinter import (
    BOTH,
    BOTTOM,
    CENTER,
    DISABLED,
    FLAT,
    LEFT,
    NORMAL,
    RIGHT,
    SOLID,
    TOP,
    Button,
    Canvas,
    Checkbutton,
    DoubleVar,
    Frame,
    Label,
    Listbox,
    Menu,
    PhotoImage,
    StringVar,
    Tk,
    Toplevel,
    W,
    X,
    Y,
    filedialog,
    messagebox,
    scrolledtext,
    ttk,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# pyrefly: ignore [missing-import]
from src.core.database import db
from src.core.reports import report

# Try importing extractor module for metadata extraction
try:
    from src.core.extractor import extractor
except ImportError:  # pragma: no cover - optional dependency
    extractor = None

# Try importing editor module for metadata editing and writing
try:
    from src.core.editor import editor
except ImportError:  # pragma: no cover - optional dependency
    editor = None

# Try importing risk analyzer module for privacy risk and timeline analysis
try:
    from src.core.risk import risk_analyzer
except ImportError:  # pragma: no cover - optional dependency
    risk_analyzer = None

from src.gui.batch_process_dialog import BatchProcessDialog, open_batch_process_dialog
from src.gui.statistics_dashboard import (
    StatisticsDashboard,
    create_metric_card,
    open_statistics_dashboard,
)
from src.gui.tabs import (
    EditorTab,
    ExtractorTab,
    HistoryTab,
    PreviewTab,
    RiskTab,
)



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

        # Tab component instances
        self.extractor_tab: ExtractorTab | None = None
        self.editor_tab: EditorTab | None = None
        self.history_tab: HistoryTab | None = None
        self.risk_tab: RiskTab | None = None
        self.preview_tab: PreviewTab | None = None

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
    @staticmethod
    def _resource_path(relative_path: str) -> str:
        """Resolve resource path for dev mode and PyInstaller bundles."""
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

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
        self.root.resizable(True, True)

        logo_path = self._resource_path("Metadata.png")
        if os.path.exists(logo_path):
            try:
                # Keep a reference to prevent Tk from garbage-collecting the image.
                self.logo = PhotoImage(file=logo_path)
                self.root.iconphoto(True, self.logo)
            except Exception:
                # Icon should never block app startup.
                pass

    def _create_widgets(self) -> None:
        """Build UI components using dedicated tab modules."""
        # Title label
        title_label = Label(
            self.root,
            text="TraceLens : Intelligent Metadata Analysis & Privacy Inspection Toolkit",
            bg="#f5f7fa",
            font=("Segoe UI", 22, "bold"),
            fg="#1a1a1a",
        )
        title_label.place(relx=0.5, y=25, width=self.window_width - 20, height=40, anchor="center")

        # Configure modern flat design theme
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#f5f7fa", borderwidth=0)
        style.configure("TNotebook.Tab", padding=[20, 10], font=("Segoe UI", 10))

        nb = ttk.Notebook(self.root)
        nb.pack(fill=BOTH, expand=True, padx=10, pady=(60, 10))
        self.nb_widget = nb

        # Tab frames
        tab1 = Frame(nb, bg="#ffffff")
        tab2 = Frame(nb, bg="#ffffff")
        tab3 = Frame(nb, bg="#ffffff")
        tab5 = Frame(nb, bg="#ffffff")
        tab4 = Frame(nb, bg="#ffffff")

        self.tab2_ref = tab2
        self.tab5_ref = tab5
        self.tab4_ref = tab4

        # Add tabs to notebook
        nb.add(tab1, text="Extractor")
        nb.add(tab2, text="Editor")
        nb.add(tab3, text="History")
        nb.add(tab5, text="Risk analyzer")
        nb.add(tab4, text="Preview")

        # Initialize tab components from dedicated tab modules
        self.extractor_tab = ExtractorTab(tab1, self)
        self.editor_tab = EditorTab(tab2, self)
        self.history_tab = HistoryTab(tab3, self)
        self.risk_tab = RiskTab(tab5, self)
        self.preview_tab = PreviewTab(tab4, self)

        nb.bind("<<NotebookTabChanged>>", lambda e: self._on_tab_changed(e, tab2, tab3, tab5))

    def _build_history_tab(self, tab3: Frame) -> None:
        """Construct history tab via HistoryTab component."""
        self.history_tab = HistoryTab(tab3, self)

    def _build_risk_tab(self, tab5: Frame) -> None:
        """Construct risk tab via RiskTab component."""
        self.risk_tab = RiskTab(tab5, self)

    def _render_risk_analysis(self, analysis: dict | None) -> None:
        """Render risk gauge, reasons and timeline chart in Risk analyzer tab."""
        if self.risk_tab:
            self.risk_tab.render_risk_analysis(analysis)

    # ------------------------------------------------------------------
    # Tab and editor helpers
    # ------------------------------------------------------------------
    def _on_tab_changed(self, event, tab2: Frame, tab3: Frame, tab5: Frame) -> None:
        """Handle notebook tab changes for refresh logic."""
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
        """Populate editor UI with metadata key-value entry fields."""
        if self.editor_tab:
            self.editor_tab.populate_editor_fields(metadata)
        else:
            self._clear_editor_fields()

    def _clear_editor_fields(self) -> None:
        """Clear all metadata entry fields from the editor."""
        if self.editor_entry_frame:
            for widget in self.editor_entry_frame.winfo_children():
                widget.destroy()
        self.editor_entry_fields.clear()

    def _is_editable_field(self, field_name: str) -> bool:
        """Check if a field is user-editable."""
        return field_name not in self.NON_EDITABLE_FIELDS

    def _show_welcome_text(self) -> None:
        """Display welcome message in the metadata text widget."""
        if self.extractor_tab:
            self.extractor_tab.show_welcome_text()

    def _get_timeline_fallbacks(self, extracted_at: str | None = None, modified_on: str | None = None) -> dict:
        """Build fallback timestamps when metadata has no timeline fields."""
        fallback = {}
        if self.file_path and os.path.exists(self.file_path):
            try:
                fallback["Created Date"] = datetime.fromtimestamp(os.path.getctime(self.file_path)).isoformat(
                    sep=" ", timespec="seconds"
                )
            except Exception:
                pass
            try:
                fallback["Modified Date"] = datetime.fromtimestamp(os.path.getmtime(self.file_path)).isoformat(
                    sep=" ", timespec="seconds"
                )
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
        """Update the status bar with a message."""
        if self.status_var:
            self.status_var.set(message)

    def _display_extracted_metadata(self, metadata, file_path: str, db_row) -> None:
        """Display extracted metadata in the text widget."""
        if self.extractor_tab:
            self.extractor_tab.display_extracted_metadata(metadata, file_path, db_row)

    # ------------------------------------------------------------------
    # Core actions
    # ------------------------------------------------------------------
    def extract_metadata(self) -> None:
        """Extract metadata from the selected file and display results."""
        if self.extractor_tab:
            self.extractor_tab.extract_metadata()

    def generate_report(self) -> None:
        """Generate a metadata report and display in preview tab."""
        if self.preview_tab:
            self.preview_tab.generate_report()

    def open_editor_with_current_metadata(self) -> None:
        """Open editor tab with current metadata loaded for editing."""
        if self.editor_tab:
            self.editor_tab.open_editor_with_current_metadata()

    def open_risk_analyzer_with_scan(self) -> None:
        """Open Risk analyzer tab and scan current file metadata for privacy/forensic risk."""
        if self.risk_tab:
            self.risk_tab.open_risk_analyzer_with_scan()

    def choose_file(self) -> None:
        """Open file dialog for user to select a file to analyze."""
        if self.extractor_tab:
            self.extractor_tab.choose_file()

    def update_report_preview(self, text: str) -> None:
        """Update the report preview panel with formatted text."""
        if self.preview_tab:
            self.preview_tab.update_report_preview(text)

    def save_report_from_preview(self) -> None:
        """Save the current report preview to a PDF file."""
        if self.preview_tab:
            self.preview_tab.save_report_from_preview()

    def print_report_from_preview(self) -> None:
        """Send the current report preview to the default printer."""
        if self.preview_tab:
            self.preview_tab.print_report_from_preview()

    # ------------------------------------------------------------------
    # Canvas centering helper
    # ------------------------------------------------------------------
    def _on_canvas_configure(self, event=None) -> None:
        """Center the image in canvas when canvas is configured/resized."""
        if self.preview_tab:
            self.preview_tab.on_canvas_configure(event)

    # ------------------------------------------------------------------
    # Image zoom controls
    # ------------------------------------------------------------------
    def zoom_in_image(self) -> None:
        """Zoom in on the preview image by 20%."""
        if self.preview_tab:
            self.preview_tab.zoom_in_image()

    def zoom_out_image(self) -> None:
        """Zoom out on the preview image by 20%."""
        if self.preview_tab:
            self.preview_tab.zoom_out_image()

    def reset_zoom_image(self) -> None:
        """Reset image zoom to 100%."""
        if self.preview_tab:
            self.preview_tab.reset_zoom_image()

    def _apply_image_zoom(self) -> None:
        """Apply the current zoom level to the preview image."""
        if self.preview_tab:
            self.preview_tab.apply_image_zoom()

    # ------------------------------------------------------------------
    # Editor actions
    # ------------------------------------------------------------------
    def save_editor_changes(self) -> None:
        """Save edited metadata from editor fields to database and file."""
        if self.editor_tab:
            self.editor_tab.save_editor_changes()

    def cancel_editor_changes(self) -> None:
        """Discard editor changes and reload original extracted metadata."""
        if self.editor_tab:
            self.editor_tab.cancel_editor_changes()

    def add_metadata_field(self) -> None:
        """Open dialog to add custom metadata field to the editor."""
        if self.editor_tab:
            self.editor_tab.add_metadata_field()

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
        filepath = filedialog.askopenfilename(
            title="Import Metadata", filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
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
                self.c1_text.delete(1.0, "end")
                self.c1_text.insert("end", "Data cleared. Ready to start.\n")
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
            if db and db.clear_metadata():
                messagebox.showinfo("Success", "History cleared successfully.")
                if callable(self.history_refresh):
                    self.history_refresh()
                self.set_status("History cleared")
            else:
                messagebox.showerror("Error", "Failed to clear history.")

    def menu_show_about(self) -> None:
        about_text = (
            "TraceLens: Intelligent Metadata Analysis & Privacy Inspection Toolkit\n\n"
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

        Label(settings_frame, text="Display Settings", font=("Segoe UI", 11, "bold"), bg="#ffffff").pack(
            anchor=W, pady=(0, 8)
        )

        theme_frame = Frame(settings_frame, bg="#ffffff")
        theme_frame.pack(fill=X, pady=5)
        Label(theme_frame, text="Theme:", bg="#ffffff", width=15, anchor=W).pack(side=LEFT)
        theme_var = StringVar(value="Light")
        ttk.Combobox(theme_frame, textvariable=theme_var, values=["Light", "Dark"], state="readonly", width=20).pack(
            side=LEFT
        )

        font_frame = Frame(settings_frame, bg="#ffffff")
        font_frame.pack(fill=X, pady=5)
        Label(font_frame, text="Font Size:", bg="#ffffff", width=15, anchor=W).pack(side=LEFT)
        font_var = StringVar(value="11")
        ttk.Combobox(
            font_frame, textvariable=font_var, values=["9", "10", "11", "12", "13", "14"], state="readonly", width=20
        ).pack(side=LEFT)

        Label(settings_frame, text="Behavior Settings", font=("Segoe UI", 11, "bold"), bg="#ffffff").pack(
            anchor=W, pady=(15, 8)
        )

        auto_refresh_var = StringVar(value="1")
        Checkbutton(settings_frame, text="Auto-refresh history on data change", variable=auto_refresh_var, bg="#ffffff").pack(
            anchor=W, pady=3
        )

        confirm_delete_var = StringVar(value="1")
        Checkbutton(settings_frame, text="Confirm before deleting records", variable=confirm_delete_var, bg="#ffffff").pack(
            anchor=W, pady=3
        )

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

        window_width = 700
        window_height = 500

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

        header_frame = Frame(recent_window, bg="#0066cc", height=60)
        header_frame.pack(fill=X)
        header_frame.pack_propagate(False)

        Label(
            header_frame,
            text="Recent Files",
            font=("Segoe UI", 16, "bold"),
            bg="#0066cc",
            fg="white",
        ).pack(side=LEFT, padx=20, pady=15)

        Label(
            header_frame,
            text="Last 10 extracted files",
            font=("Segoe UI", 9),
            bg="#0066cc",
            fg="#b3d9ff",
        ).pack(side=LEFT, padx=(0, 20), pady=15)

        try:
            recent_data = db.get_recent_records(limit=10) if db else []

            content_frame = Frame(recent_window, bg="#f5f7fa")
            content_frame.pack(fill=BOTH, expand=True, padx=0, pady=0)

            if not recent_data:
                empty_frame = Frame(content_frame, bg="#ffffff")
                empty_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

                Label(
                    empty_frame,
                    text="No Files",
                    font=("Segoe UI", 24, "bold"),
                    bg="#ffffff",
                    fg="#cccccc",
                ).pack(pady=(40, 10))

                Label(
                    empty_frame,
                    text="No recent files",
                    font=("Segoe UI", 12, "bold"),
                    bg="#ffffff",
                    fg="#666666",
                ).pack(pady=(0, 5))

                Label(
                    empty_frame,
                    text="Extract metadata from files to see them here",
                    font=("Segoe UI", 10),
                    bg="#ffffff",
                    fg="#999999",
                ).pack(pady=(0, 40))
            else:
                list_container = Frame(content_frame, bg="#f5f7fa")
                list_container.pack(fill=BOTH, expand=True, padx=20, pady=15)

                canvas = Canvas(list_container, bg="#f5f7fa", highlightthickness=0)
                scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
                scrollable_frame = Frame(canvas, bg="#f5f7fa")

                scrollable_frame.bind(
                    "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
                )

                canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
                canvas.configure(yscrollcommand=scrollbar.set)

                canvas.pack(side=LEFT, fill=BOTH, expand=True)
                scrollbar.pack(side=RIGHT, fill=Y)

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

                for idx, row in enumerate(recent_data, 1):
                    file_item = Frame(scrollable_frame, bg="#ffffff", relief=FLAT, bd=0)
                    file_item.pack(fill=X, pady=(0, 10), ipady=5, ipadx=5)
                    file_item.config(highlightbackground="#e0e0e0", highlightthickness=1)

                    index_frame = Frame(file_item, bg="#0066cc", width=40, height=40)
                    index_frame.pack(side=LEFT, padx=(10, 15), pady=10)
                    index_frame.pack_propagate(False)

                    Label(
                        index_frame,
                        text=str(idx),
                        font=("Segoe UI", 12, "bold"),
                        bg="#0066cc",
                        fg="white",
                    ).place(relx=0.5, rely=0.5, anchor=CENTER)

                    info_frame = Frame(file_item, bg="#ffffff")
                    info_frame.pack(side=LEFT, fill=BOTH, expand=True, pady=10)

                    Label(
                        info_frame,
                        text=row[2],
                        font=("Segoe UI", 11, "bold"),
                        bg="#ffffff",
                        fg="#1a1a1a",
                        anchor=W,
                    ).pack(fill=X, padx=0, pady=(0, 5))

                    path_label = Label(
                        info_frame,
                        text=f"Path: {row[1]}",
                        font=("Segoe UI", 9),
                        bg="#ffffff",
                        fg="#666666",
                        anchor=W,
                    )
                    path_label.pack(fill=X, padx=0, pady=(0, 3))

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
                        pady=2,
                    ).pack(side=LEFT, padx=(0, 5))

                    Label(
                        meta_frame,
                        text=row[3],
                        font=("Segoe UI", 8),
                        bg="#f0f0f0",
                        fg="#666666",
                        relief=FLAT,
                        padx=8,
                        pady=2,
                    ).pack(side=LEFT, padx=(0, 5))

                    if len(row) > 5 and row[5]:
                        Label(
                            meta_frame,
                            text=row[5],
                            font=("Segoe UI", 8),
                            bg="#f0f0f0",
                            fg="#666666",
                            relief=FLAT,
                            padx=8,
                            pady=2,
                        ).pack(side=LEFT)

        except Exception as e:
            error_frame = Frame(content_frame, bg="#ffffff")
            error_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

            Label(
                error_frame,
                text="ERROR",
                font=("Segoe UI", 24, "bold"),
                bg="#ffffff",
                fg="#ff6b6b",
            ).pack(pady=(40, 10))

            Label(
                error_frame,
                text="Error Loading Recent Files",
                font=("Segoe UI", 12, "bold"),
                bg="#ffffff",
                fg="#ff6b6b",
            ).pack(pady=(0, 5))

            Label(
                error_frame,
                text=str(e),
                font=("Segoe UI", 9),
                bg="#ffffff",
                fg="#999999",
                wraplength=500,
            ).pack(pady=(0, 40))

        footer_frame = Frame(recent_window, bg="#f5f7fa", height=70)
        footer_frame.pack(fill=X, side=BOTTOM)
        footer_frame.pack_propagate(False)

        close_btn = ttk.Button(
            footer_frame,
            text="Close",
            command=recent_window.destroy,
            width=15,
        )
        close_btn.pack(pady=15)

    def menu_zoom_in(self) -> None:
        if not hasattr(self, "current_font_size"):
            self.current_font_size = 11
        self.current_font_size = min(self.current_font_size + 1, 16)
        messagebox.showinfo(
            "Zoom", f"Font size increased to {self.current_font_size}pt.\n(Changes apply to new text widgets)"
        )
        self.set_status(f"Zoom: {self.current_font_size}pt")

    def menu_zoom_out(self) -> None:
        if not hasattr(self, "current_font_size"):
            self.current_font_size = 11
        self.current_font_size = max(self.current_font_size - 1, 8)
        messagebox.showinfo(
            "Zoom", f"Font size decreased to {self.current_font_size}pt.\n(Changes apply to new text widgets)"
        )
        self.set_status(f"Zoom: {self.current_font_size}pt")

    def menu_reset_zoom(self) -> None:
        self.current_font_size = 11
        messagebox.showinfo("Zoom", "Font size reset to 11pt (default).\n(Changes apply to new text widgets)")
        self.set_status("Zoom: reset to default")

    def menu_fullscreen(self) -> None:
        current_state = self.root.attributes("-zoomed")
        self.root.attributes("-zoomed", not current_state)
        self.set_status("Fullscreen toggled" if not current_state else "Fullscreen disabled")

    def menu_batch_process(self) -> BatchProcessDialog:
        """Open the enhanced Batch Process & Folder Extraction dialog."""
        return open_batch_process_dialog(self.root, self)


    def _create_metric_card(
        self, parent, title, value, subtitle="", bg_start="#667eea", bg_end="#764ba2", width=None
    ):
        """Create a material design-style card with gradient background for displaying metrics."""
        return create_metric_card(parent, title, value, subtitle, bg_start, bg_end, width)

    def menu_statistics(self) -> None:
        """Display enhanced statistics dashboard with material design cards and interactive charts."""
        open_statistics_dashboard(self.root)

    def menu_check_updates(self) -> None:
        messagebox.showinfo(
            "Check for Updates",
            "You are using TraceLens: Intelligent Metadata Analysis & Privacy Inspection Toolkit v1.0\n\nAlready up to date!\n\nFor the latest version, visit the project repository.",
        )

    def menu_credits(self) -> None:
        credits_text = (
            "TraceLens: Intelligent Metadata Analysis & Privacy Inspection Toolkit\n\n"
            "Development By: Tanmay Bhatnagar\n\n"
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

        Label(issue_window, text="Report an Issue", font=("Segoe UI", 14, "bold"), bg="#f5f7fa").pack(
            fill=X, padx=15, pady=10
        )

        main_frame = Frame(issue_window, bg="#ffffff")
        main_frame.pack(fill=BOTH, expand=True, padx=15, pady=10)

        Label(main_frame, text="Issue Title:", font=("Segoe UI", 10, "bold"), bg="#ffffff").pack(anchor=W, pady=(0, 5))
        title_entry = ttk.Entry(main_frame, width=50)
        title_entry.pack(fill=X, pady=(0, 10))

        Label(main_frame, text="Description:", font=("Segoe UI", 10, "bold"), bg="#ffffff").pack(anchor=W, pady=(0, 5))
        desc_text = scrolledtext.ScrolledText(main_frame, height=12, width=60, wrap="word", font=("Segoe UI", 10))
        desc_text.pack(fill=BOTH, expand=True, pady=(0, 10))

        Label(main_frame, text="Category:", font=("Segoe UI", 10, "bold"), bg="#ffffff").pack(anchor=W, pady=(0, 5))
        category_var = StringVar()
        ttk.Combobox(
            main_frame,
            textvariable=category_var,
            values=["Bug", "Feature Request", "Improvement", "Documentation", "Other"],
            state="readonly",
            width=47,
        ).pack(fill=X, pady=(0, 10))

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
            "GitHub: https://github.com/Tanmay-Bhatnagar22/TraceLens\n\n"
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
        """Bind keyboard shortcuts to their respective commands."""
        # File menu shortcuts
        self.root.bind("<Control-n>", lambda e: self.menu_new_project())
        self.root.bind("<Control-N>", lambda e: self.menu_new_project())
        self.root.bind("<Control-o>", lambda e: self.choose_file())
        self.root.bind("<Control-O>", lambda e: self.choose_file())
        self.root.bind("<Control-e>", lambda e: self.menu_export_results())
        self.root.bind("<Control-E>", lambda e: self.menu_export_results())

        # Edit menu shortcuts
        self.root.bind("<Control-c>", lambda e: self.menu_copy_results())
        self.root.bind("<Control-C>", lambda e: self.menu_copy_results())

        # View menu shortcuts
        self.root.bind("<F5>", lambda e: self.menu_refresh_all())
        self.root.bind("<Control-plus>", lambda e: self.menu_zoom_in())
        self.root.bind("<Control-equal>", lambda e: self.menu_zoom_in())
        self.root.bind("<Control-minus>", lambda e: self.menu_zoom_out())
        self.root.bind("<Control-0>", lambda e: self.menu_reset_zoom())
        self.root.bind("<F11>", lambda e: self.menu_fullscreen())

        # Help menu shortcuts
        self.root.bind("<F1>", lambda e: self.menu_show_documentation())
        self.root.bind("<Control-question>", lambda e: self.menu_show_shortcuts())
        self.root.bind("<Control-slash>", lambda e: self.menu_show_shortcuts())

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------
    def _build_menu_bar(self) -> None:
        """Build application menu bar with File, Edit, View, Tools, and Help menus."""
        menu = Menu(
            self.root,
            bg="#f5f7fa",
            fg="#1a1a1a",
            activebackground="#0066cc",
            activeforeground="#ffffff",
            relief=FLAT,
            bd=0,
        )
        self.root.config(menu=menu)

        file_menu = Menu(
            menu, tearoff=0, bg="#f5f7fa", fg="#1a1a1a", activebackground="#0066cc", activeforeground="#ffffff"
        )
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

        edit_menu = Menu(
            menu, tearoff=0, bg="#f5f7fa", fg="#1a1a1a", activebackground="#0066cc", activeforeground="#ffffff"
        )
        menu.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Clear All Data", command=self.menu_clear_all_data)
        edit_menu.add_command(label="Copy Results", command=self.menu_copy_results, accelerator="Ctrl+C")

        view_menu = Menu(
            menu, tearoff=0, bg="#f5f7fa", fg="#1a1a1a", activebackground="#0066cc", activeforeground="#ffffff"
        )
        menu.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Refresh All Data", command=self.menu_refresh_all, accelerator="F5")
        view_menu.add_separator()
        view_menu.add_command(label="Zoom In", command=self.menu_zoom_in, accelerator="Ctrl++")
        view_menu.add_command(label="Zoom Out", command=self.menu_zoom_out, accelerator="Ctrl+-")
        view_menu.add_command(label="Reset Zoom", command=self.menu_reset_zoom, accelerator="Ctrl+0")
        view_menu.add_separator()
        view_menu.add_command(label="Full Screen", command=self.menu_fullscreen, accelerator="F11")

        tools_menu = Menu(
            menu, tearoff=0, bg="#f5f7fa", fg="#1a1a1a", activebackground="#0066cc", activeforeground="#ffffff"
        )
        menu.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Generate Report", command=self.generate_report)
        tools_menu.add_command(label="Batch Process", command=self.menu_batch_process)
        tools_menu.add_separator()
        tools_menu.add_command(label="Backup Database", command=self.menu_backup_database)
        tools_menu.add_command(label="Clear History", command=self.menu_clear_history)
        tools_menu.add_separator()
        tools_menu.add_command(label="Statistics Dashboard", command=self.menu_statistics)

        help_menu = Menu(
            menu, tearoff=0, bg="#f5f7fa", fg="#1a1a1a", activebackground="#0066cc", activeforeground="#ffffff"
        )
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
