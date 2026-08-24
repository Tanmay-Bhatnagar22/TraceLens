"""History tab module for TraceLens GUI.

Handles metadata history browsing, filtering, sorting, exporting, and deletion.
"""

from __future__ import annotations

import json
from datetime import datetime
from tkinter import (
    BOTH,
    BOTTOM,
    CENTER,
    DISABLED,
    END,
    LEFT,
    NO,
    NORMAL,
    RIGHT,
    W,
    X,
    Y,
    YES,
    Frame,
    Label,
    StringVar,
    messagebox,
    ttk,
)
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.gui.gui import MetadataAnalyzerApp

# Try importing database module
try:
    from src.core.database import db
except ImportError:  # pragma: no cover - optional dependency
    db = None

# Try importing risk analyzer module
try:
    from src.core.risk import risk_analyzer
except ImportError:  # pragma: no cover - optional dependency
    risk_analyzer = None


class HistoryTab:
    """Component managing the History tab UI and database record interactions."""

    def __init__(self, parent_frame: Frame, app: MetadataAnalyzerApp) -> None:
        self.parent = parent_frame
        self.app = app

        self.search_var: StringVar | None = None
        self.filter_var: StringVar | None = None
        self.date_var: StringVar | None = None
        self.sort_var: StringVar | None = None

        self.tree: ttk.Treeview | None = None
        self.search_entry: ttk.Entry | None = None

        self.build_ui()

    def build_ui(self) -> None:
        """Construct the History tab UI widgets."""
        self.search_var = StringVar(master=self.parent)
        self.filter_var = StringVar(master=self.parent)
        self.date_var = StringVar(master=self.parent)
        self.sort_var = StringVar(master=self.parent)

        history_container = Frame(self.parent, bg="#ffffff")
        history_container.pack(fill=BOTH, expand=True, padx=10, pady=10)

        search_row1 = Frame(history_container, bg="#ffffff")
        search_row1.pack(fill=X, pady=(0, 12))

        Label(search_row1, text="Search:", bg="#ffffff", font=("Segoe UI", 10, "bold"), fg="#1a1a1a").pack(
            side=LEFT, padx=(0, 8)
        )
        self.search_entry = ttk.Entry(search_row1, textvariable=self.search_var, width=25, font=("Segoe UI", 10))
        self.search_entry.pack(side=LEFT, padx=(0, 15))

        Label(search_row1, text="File Type:", bg="#ffffff", font=("Segoe UI", 10, "bold"), fg="#1a1a1a").pack(
            side=LEFT, padx=(0, 8)
        )
        filter_combo = ttk.Combobox(
            search_row1, textvariable=self.filter_var, width=16, state="readonly", font=("Segoe UI", 10)
        )
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
        self.filter_var.set("All")
        filter_combo.pack(side=LEFT, padx=(0, 15))

        Label(search_row1, text="Date Range:", bg="#ffffff", font=("Segoe UI", 10, "bold"), fg="#1a1a1a").pack(
            side=LEFT, padx=(0, 8)
        )
        date_combo = ttk.Combobox(
            search_row1, textvariable=self.date_var, width=17, state="readonly", font=("Segoe UI", 10)
        )
        date_combo["values"] = ["All Time", "Today", "This Week", "This Month", "Last 30 Days"]
        self.date_var.set("All Time")
        date_combo.pack(side=LEFT, padx=(0, 15))

        Label(search_row1, text="Sort by:", bg="#ffffff", font=("Segoe UI", 10, "bold"), fg="#1a1a1a").pack(
            side=LEFT, padx=(0, 8)
        )
        sort_combo = ttk.Combobox(
            search_row1, textvariable=self.sort_var, width=20, state="readonly", font=("Segoe UI", 10)
        )
        sort_combo["values"] = [
            "Date (Newest)",
            "Date (Oldest)",
            "Name (A-Z)",
            "Name (Z-A)",
            "Size (Largest)",
            "Size (Smallest)",
        ]
        self.sort_var.set("Date (Newest)")
        sort_combo.pack(side=LEFT, padx=(0, 15))

        tree_frame = Frame(history_container, bg="#ffffff")
        tree_frame.pack(fill=BOTH, expand=True)

        columns = (
            "S.No",
            "File Path",
            "File Name",
            "File Size",
            "File Type",
            "Risk",
            "Extracted At",
            "Modified On",
            "Record ID",
        )
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")

        for col in columns:
            self.tree.heading(col, text=col)
            if col == "S.No":
                self.tree.column(col, stretch=NO, minwidth=50, width=60, anchor=CENTER)
            elif col == "File Path":
                self.tree.column(col, stretch=YES, minwidth=200, width=240, anchor=W)
            elif col == "File Name":
                self.tree.column(col, stretch=YES, minwidth=140, width=170, anchor=W)
            elif col == "File Size":
                self.tree.column(col, stretch=NO, minwidth=80, width=100, anchor=CENTER)
            elif col == "File Type":
                self.tree.column(col, stretch=NO, minwidth=70, width=80, anchor=CENTER)
            elif col == "Risk":
                self.tree.column(col, stretch=NO, minwidth=75, width=90, anchor=CENTER)
            elif col == "Extracted At":
                self.tree.column(col, stretch=NO, minwidth=140, width=160, anchor=CENTER)
            elif col == "Modified On":
                self.tree.column(col, stretch=NO, minwidth=140, width=160, anchor=CENTER)
            elif col == "Record ID":
                self.tree.column(col, stretch=NO, minwidth=0, width=0, anchor=CENTER)

        self.tree.pack(side=LEFT, fill=BOTH, expand=True)

        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        v_scrollbar.pack(side=RIGHT, fill=Y)
        self.tree.configure(yscrollcommand=v_scrollbar.set)

        h_scrollbar = ttk.Scrollbar(history_container, orient="horizontal", command=self.tree.xview)
        h_scrollbar.pack(side=BOTTOM, fill=X, pady=(4, 0))
        self.tree.configure(xscrollcommand=h_scrollbar.set)

        button_frame = Frame(history_container, bg="#ffffff")
        button_frame.pack(fill=X, pady=(12, 0))

        for i in range(9):
            button_frame.columnconfigure(i, weight=1, uniform="buttons")

        clear_btn = ttk.Button(button_frame, text="Clear Filters", command=self.clear_filters)
        export_csv_btn = ttk.Button(button_frame, text="Export CSV", command=lambda: self.export_handler("csv"))
        export_excel_btn = ttk.Button(button_frame, text="Export Excel", command=lambda: self.export_handler("excel"))
        export_json_btn = ttk.Button(button_frame, text="Export JSON", command=lambda: self.export_handler("json"))
        export_xml_btn = ttk.Button(button_frame, text="Export XML", command=lambda: self.export_handler("xml"))
        export_pdf_btn = ttk.Button(button_frame, text="Export PDF", command=lambda: self.export_handler("pdf"))
        refresh_btn = ttk.Button(button_frame, text="Refresh", command=self.refresh_data)
        delete_all_btn = ttk.Button(button_frame, text="Delete All", command=self.delete_all_records)
        delete_btn = ttk.Button(button_frame, text="Delete", command=self.delete_selected_record)

        clear_btn.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        export_csv_btn.grid(row=0, column=1, padx=6, pady=6, sticky="ew")
        export_excel_btn.grid(row=0, column=2, padx=6, pady=6, sticky="ew")
        export_json_btn.grid(row=0, column=3, padx=6, pady=6, sticky="ew")
        export_xml_btn.grid(row=0, column=4, padx=6, pady=6, sticky="ew")
        export_pdf_btn.grid(row=0, column=5, padx=6, pady=6, sticky="ew")
        refresh_btn.grid(row=0, column=6, padx=6, pady=6, sticky="ew")
        delete_all_btn.grid(row=0, column=7, padx=6, pady=6, sticky="ew")
        delete_btn.grid(row=0, column=8, padx=6, pady=6, sticky="ew")

        self.search_var.trace("w", lambda *args: self.load_data())
        self.filter_var.trace("w", lambda *args: self.load_data())
        self.date_var.trace("w", lambda *args: self.load_data())
        self.sort_var.trace("w", lambda *args: self.load_data())

        self.tree.bind("<Double-1>", self.on_tree_double_click)

        self.load_data()
        self.app.history_refresh = self.load_data

    @staticmethod
    def _humanize(dt_str: str) -> str:
        if not dt_str:
            return ""
        try:
            return datetime.fromisoformat(dt_str).strftime("%b %d, %Y %I:%M %p")
        except Exception:
            return dt_str

    def load_data(self) -> list:
        """Fetch filtered records from database and update treeview."""
        if not db or not self.tree or not self.search_var:
            return []
        search_val = self.search_var.get() if self.search_var else ""
        filter_val = self.filter_var.get() if self.filter_var else "All"
        date_val = self.date_var.get() if self.date_var else "All Time"
        sort_val = self.sort_var.get() if self.sort_var else "Date (Newest)"

        data = db.filter_and_search_data(search_val, filter_val, date_val, sort_val)
        self.tree.delete(*self.tree.get_children())
        risk_cache = {}
        for idx, row in enumerate(data, start=1):
            extracted_at = self._humanize(row[5])
            modified_on = self._humanize(row[6])

            # Determine risk rating
            risk_level = "LOW"
            if risk_analyzer and len(row) > 7 and row[7]:
                try:
                    cache_key = (row[0], row[5], row[6])
                    if cache_key in risk_cache:
                        risk_level = risk_cache[cache_key]
                    else:
                        parsed_meta = json.loads(row[7]) if isinstance(row[7], str) else (row[7] or {})
                        res = risk_analyzer.analyze_metadata(parsed_meta, row[1])
                        risk_level = res.get("risk_level", "LOW")
                        risk_cache[cache_key] = risk_level
                except Exception:
                    risk_level = "LOW"

            self.tree.insert(
                "",
                END,
                values=(idx, row[1], row[2], row[3], row[4], risk_level, extracted_at, modified_on, row[0]),
            )
        return data

    def clear_filters(self) -> None:
        """Reset search and filter controls to default values."""
        if self.search_var:
            self.search_var.set("")
        if self.filter_var:
            self.filter_var.set("All")
        if self.date_var:
            self.date_var.set("All Time")
        if self.sort_var:
            self.sort_var.set("Date (Newest)")
        if self.search_entry:
            self.search_entry.focus_set()
        self.load_data()

    def refresh_data(self) -> None:
        """Reload history data."""
        self.load_data()

    def delete_selected_record(self) -> None:
        """Delete currently highlighted record in the treeview."""
        if not self.tree or not db:
            return
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a record to delete.")
            return
        record_values = self.tree.item(selected[0])["values"]
        record_id = record_values[-1]
        if messagebox.askyesno("Confirm Delete", f"Delete record ID: {record_id}?"):
            if db.delete_record(record_id):
                messagebox.showinfo("Success", "Record deleted successfully.")
            else:
                messagebox.showerror("Error", "Failed to delete record.")
            self.load_data()

    def delete_all_records(self) -> None:
        """Delete all records in the database."""
        if not db:
            return
        if messagebox.askyesno("Confirm Delete", "Delete all metadata records? This cannot be undone."):
            if db.clear_metadata():
                messagebox.showinfo("Success", "All records deleted.")
            else:
                messagebox.showerror("Error", "Failed to delete records.")
            self.load_data()

    def export_handler(self, fmt: str) -> None:
        """Export current filtered history data to specified format."""
        if not db:
            return
        data = self.load_data()
        if not data:
            messagebox.showwarning("No Data", "No records to export with current filters.")
            return
        db.export_data(fmt, data)
        messagebox.showinfo("Export", f"Exported data as {fmt.upper()}.")

    def on_tree_double_click(self, event: Any) -> None:
        """Load selected record back into the Extractor view."""
        if not self.tree or not db:
            return
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0])["values"]
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

        self.app.file_path = row[1]
        full_meta_json = row[7]
        try:
            self.app.extracted_metadata = (
                json.loads(full_meta_json) if isinstance(full_meta_json, str) else (full_meta_json or {})
            )
        except Exception:
            self.app.extracted_metadata = {}

        if risk_analyzer and isinstance(self.app.extracted_metadata, dict):
            try:
                self.app.risk_analysis = risk_analyzer.analyze_metadata(
                    self.app.extracted_metadata,
                    self.app.file_path,
                    fallback_timestamps=self.app._get_timeline_fallbacks(
                        extracted_at=row[5] if len(row) > 5 else None,
                        modified_on=row[6] if len(row) > 6 else None,
                    ),
                )
            except Exception:
                self.app.risk_analysis = None

        if self.app.c1_text:
            self.app.c1_text.config(state=NORMAL)
            self.app.c1_text.delete(1.0, END)
            self.app.c1_text.insert(END, "File Information\n", "header")
            self.app.c1_text.insert(END, "\n")
            self.app.c1_text.insert(END, f"Filename:  {row[2]}\n", "bold")
            self.app.c1_text.insert(END, f"Path:  {row[1]}\n", "bold")
            self.app.c1_text.insert(END, f"Type:  {row[4]}\n", "bold")
            self.app.c1_text.insert(END, f"Size:  {row[3]}\n", "bold")
            self.app.c1_text.insert(END, f"Extracted At:  {self._humanize(row[5])}\n", "bold")
            self.app.c1_text.insert(END, f"Modified On:  {self._humanize(row[6])}\n\n", "bold")
            if isinstance(self.app.extracted_metadata, dict):
                for k, v in self.app.extracted_metadata.items():
                    self.app.c1_text.insert(END, f"{k}: {v}\n")
            else:
                self.app.c1_text.insert(END, f"{self.app.extracted_metadata}\n")
            self.app.c1_text.config(state=DISABLED)

        try:
            if self.app.nb_widget is not None:
                tabs = self.app.nb_widget.tabs()
                if tabs:
                    self.app.nb_widget.select(tabs[0])
        except Exception:
            pass
