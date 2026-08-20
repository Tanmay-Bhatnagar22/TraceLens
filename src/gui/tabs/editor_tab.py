"""Editor tab module for TraceLens GUI.

Handles metadata editing, adding custom fields, field validation, and persistence.
"""

from __future__ import annotations

import os
from datetime import datetime
from tkinter import (
    BOTH,
    BOTTOM,
    FLAT,
    LEFT,
    NW,
    SOLID,
    W,
    X,
    Canvas,
    Frame,
    Label,
    Toplevel,
    messagebox,
    ttk,
)
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.gui.gui import MetadataAnalyzerApp

# Try importing editor module for metadata editing and writing
try:
    from src.core.editor import editor
except ImportError:  # pragma: no cover - optional dependency
    editor = None

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


class EditorTab:
    """Component managing the Editor tab UI and metadata modification workflows."""

    NON_EDITABLE_FIELDS = {"File Name", "File Size", "File Type", "Extracted At", "Modified On"}

    def __init__(self, parent_frame: Frame, app: MetadataAnalyzerApp) -> None:
        self.parent = parent_frame
        self.app = app
        self.build_ui()

    def build_ui(self) -> None:
        """Construct the Editor tab UI widgets."""
        c2 = Frame(self.parent, bg="#ffffff")
        c2.pack(fill=BOTH, expand=1)

        editor_controls = Frame(c2, bg="#f8f9fa", height=60)
        editor_controls.pack(side=BOTTOM, fill=X)
        editor_controls.pack_propagate(False)

        ttk.Button(editor_controls, text="Save Changes", command=self.save_editor_changes).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(editor_controls, text="Cancel", command=self.cancel_editor_changes).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(editor_controls, text="Add Metadata", command=self.add_metadata_field).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(editor_controls, text="Generate Report", command=self.app.generate_report).pack(side=LEFT, padx=10, pady=10)

        editor_status_frame = Frame(c2, bg="#2c3e50", height=30)
        editor_status_frame.pack(side=BOTTOM, fill=X)
        editor_status_frame.pack_propagate(False)
        self.app.editor_status = Label(
            editor_status_frame,
            text="",
            relief=FLAT,
            anchor=W,
            font=("Segoe UI", 9),
            background="#2c3e50",
            foreground="#ffffff",
            padx=10,
        )
        self.app.editor_status.pack(side=LEFT, fill=X, expand=True, pady=8)

        editor_fields_container = Frame(c2, bg="#ffffff")
        editor_fields_container.pack(fill=BOTH, expand=True)

        Label(
            editor_fields_container,
            text="Metadata Editor",
            bg="#ffffff",
            font=("Segoe UI", 14, "bold"),
            fg="#1a1a1a",
            anchor=W,
        ).pack(fill=X, padx=15, pady=(12, 4))

        self.app.editor_canvas = Canvas(editor_fields_container, bg="#ffffff", highlightthickness=0, bd=0)
        self.app.editor_canvas.pack(side=LEFT, fill=BOTH, expand=True)

        self.app.editor_entry_frame = Frame(self.app.editor_canvas, bg="#ffffff")
        self.app.editor_canvas.create_window((0, 0), window=self.app.editor_entry_frame, anchor=NW)
        self.app.editor_entry_frame.bind(
            "<Configure>",
            lambda e: self.app.editor_canvas.configure(scrollregion=self.app.editor_canvas.bbox("all"))
            if self.app.editor_canvas
            else None,
        )

        def _on_mousewheel(event):
            delta_steps = 0
            if hasattr(event, "delta") and event.delta:
                delta_steps = int(-1 * (event.delta / 120))
            elif getattr(event, "num", None) == 4:
                delta_steps = -1
            elif getattr(event, "num", None) == 5:
                delta_steps = 1
            if delta_steps and self.app.editor_canvas:
                self.app.editor_canvas.yview_scroll(delta_steps, "units")

        self.app.editor_canvas.bind("<MouseWheel>", _on_mousewheel)
        self.app.editor_canvas.bind("<Button-4>", _on_mousewheel)
        self.app.editor_canvas.bind("<Button-5>", _on_mousewheel)
        self.app.editor_entry_frame.bind("<MouseWheel>", _on_mousewheel)
        self.app.editor_entry_frame.bind("<Button-4>", _on_mousewheel)
        self.app.editor_entry_frame.bind("<Button-5>", _on_mousewheel)

    def populate_editor_fields(self, metadata: dict) -> None:
        """Populate editor UI with metadata key-value entry fields."""
        self.clear_editor_fields()
        if not metadata or not isinstance(metadata, dict) or not self.app.editor_entry_frame:
            return
        for key, value in metadata.items():
            field_frame = Frame(self.app.editor_entry_frame, bg="#ffffff")
            field_frame.pack(fill=X, padx=15, pady=8)

            label = Label(
                field_frame,
                text=f"{key}:",
                bg="#ffffff",
                font=("Segoe UI", 10, "bold"),
                fg="#1a1a1a",
                width=20,
                anchor=W,
            )
            label.pack(side=LEFT, padx=(0, 10))

            entry = ttk.Entry(field_frame, font=("Segoe UI", 10), width=50)
            entry.pack(side=LEFT, fill=X, expand=True)
            entry.insert(0, str(value))
            if not self.is_editable_field(key):
                entry.state(["disabled"])

            self.app.editor_entry_fields[key] = entry

    def clear_editor_fields(self) -> None:
        """Clear all metadata entry fields from the editor."""
        if self.app.editor_entry_frame:
            for widget in self.app.editor_entry_frame.winfo_children():
                widget.destroy()
        self.app.editor_entry_fields.clear()

    def is_editable_field(self, field_name: str) -> bool:
        """Check if a field is user-editable."""
        return field_name not in self.NON_EDITABLE_FIELDS

    def open_editor_with_current_metadata(self) -> None:
        """Open editor tab with current metadata loaded for editing."""
        if not self.app.extracted_metadata or not self.app.file_path:
            messagebox.showwarning("No Data", "Please extract metadata first.")
            try:
                if self.app.nb_widget is not None:
                    tabs = self.app.nb_widget.tabs()
                    if tabs:
                        self.app.nb_widget.select(tabs[0])
            except Exception:
                pass
            return

        if self.app.extracted_metadata and isinstance(self.app.extracted_metadata, dict):
            self.populate_editor_fields(self.app.extracted_metadata)
            if self.app.editor_status:
                self.app.editor_status.config(text="", fg="#555555")

        if self.app.nb_widget is not None and self.app.tab2_ref is not None:
            self.app.nb_widget.select(self.app.tab2_ref)

    def save_editor_changes(self) -> None:
        """Save edited metadata from editor fields to database and file."""
        if not self.app.file_path or not self.app.extracted_metadata:
            messagebox.showwarning("No Data", "No metadata loaded to save.")
            return

        try:
            edited_metadata = {}
            headers = {}

            for field_name, entry_widget in self.app.editor_entry_fields.items():
                value = entry_widget.get().strip()
                if value:
                    if field_name in self.NON_EDITABLE_FIELDS:
                        headers[field_name] = value
                    else:
                        edited_metadata[field_name] = value

            if not headers.get("File Name") and self.app.file_path:
                headers["File Name"] = os.path.basename(self.app.file_path)
            if not headers.get("File Size") and self.app.file_path:
                try:
                    headers["File Size"] = str(os.path.getsize(self.app.file_path))
                except Exception:
                    pass
            if not headers.get("File Type") and self.app.file_path:
                headers["File Type"] = os.path.splitext(self.app.file_path)[1].lstrip(".")

            if not edited_metadata:
                messagebox.showwarning("Empty Metadata", "Please enter at least one metadata field.")
                return

            if not editor:
                messagebox.showerror("Error", "Editor module not available.")
                return

            valid, error_msg = editor.validate_metadata({"metadata": edited_metadata, "headers": headers})
            if not valid:
                if self.app.editor_status:
                    self.app.editor_status.config(text=error_msg, fg="#dc3545")
                messagebox.showerror("Validation Error", error_msg)
                return

            if db:
                db_success, db_message = db.save_edited_metadata(
                    self.app.file_path, {"metadata": edited_metadata, "headers": headers}
                )
                if not db_success:
                    if self.app.editor_status:
                        self.app.editor_status.config(text=db_message, fg="#dc3545")
                    messagebox.showerror("Database Error", db_message)
                    return
            else:
                db_success = False
                db_message = "Database not available"

            file_success, file_message = editor.write_metadata_to_file(self.app.file_path, edited_metadata)

            self.app.extracted_metadata = edited_metadata
            if risk_analyzer:
                try:
                    self.app.risk_analysis = risk_analyzer.analyze_metadata(
                        self.app.extracted_metadata,
                        self.app.file_path,
                        fallback_timestamps=self.app._get_timeline_fallbacks(
                            extracted_at=datetime.now().isoformat(sep=" ", timespec="seconds")
                        ),
                    )
                except Exception:
                    self.app.risk_analysis = None
            self.app._render_risk_analysis(self.app.risk_analysis)

            if file_success:
                if self.app.editor_status:
                    self.app.editor_status.config(text="Saved to database and file", fg="#28a745")
                messagebox.showinfo("Success", "✓ Database updated\n✓ File metadata updated")
            else:
                if self.app.editor_status:
                    self.app.editor_status.config(text="Saved to database only", fg="#ff8c00")
                messagebox.showwarning("Partial Success", f"✓ Database updated\n⚠ File: {file_message}")

            try:
                if callable(self.app.history_refresh):
                    self.app.history_refresh()
            except Exception:
                pass

        except Exception as e:
            error_msg = f"Failed to save: {str(e)}"
            if self.app.editor_status:
                self.app.editor_status.config(text=error_msg, fg="#dc3545")
            messagebox.showerror("Error", error_msg)

    def cancel_editor_changes(self) -> None:
        """Discard editor changes and reload original extracted metadata."""
        if not self.app.file_path or not self.app.extracted_metadata:
            self.clear_editor_fields()
            if self.app.editor_status:
                self.app.editor_status.config(text="", fg="#555555")
            return

        if messagebox.askyesno("Cancel Changes", "Discard all changes and reload original metadata?"):
            try:
                self.populate_editor_fields(self.app.extracted_metadata)
                if self.app.editor_status:
                    self.app.editor_status.config(text="Changes discarded", fg="#555555")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to reload: {str(e)}")

    def add_metadata_field(self) -> None:
        """Open dialog to add custom metadata field to the editor."""
        if not self.app.file_path or not self.app.extracted_metadata:
            messagebox.showwarning("No Data", "Please extract metadata first before adding custom fields.")
            return

        if not self.app.root:
            return

        dialog = Toplevel(self.app.root)
        dialog.title("Add Metadata Field")
        dialog.geometry("550x320")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.transient(self.app.root)

        dialog.update_idletasks()
        parent_x = self.app.root.winfo_x()
        parent_y = self.app.root.winfo_y()
        parent_width = self.app.root.winfo_width()
        parent_height = self.app.root.winfo_height()

        dialog_width = dialog.winfo_width()
        dialog_height = dialog.winfo_height()

        center_x = parent_x + (parent_width // 2) - (dialog_width // 2)
        center_y = parent_y + (parent_height // 2) - (dialog_height // 2)

        dialog.geometry(f"+{center_x}+{center_y}")

        main_frame = Frame(dialog, bg="#ffffff", padx=25, pady=25)
        main_frame.pack(fill=BOTH, expand=True)

        title_label = Label(
            main_frame, text="Add Custom Metadata", bg="#ffffff", font=("Segoe UI", 13, "bold"), fg="#1a1a1a"
        )
        title_label.pack(anchor=W, pady=(0, 20))

        desc_label = Label(
            main_frame,
            text="Add new metadata field for your file (e.g., GPS location, camera info, custom tags)",
            bg="#ffffff",
            font=("Segoe UI", 9),
            fg="#666666",
            wraplength=500,
            justify=LEFT,
        )
        desc_label.pack(anchor=W, pady=(0, 18))

        field_name_label = Label(
            main_frame, text="Field Name:", bg="#ffffff", font=("Segoe UI", 11, "bold"), fg="#333333"
        )
        field_name_label.pack(anchor=W, pady=(0, 8))

        field_name_entry = ttk.Entry(main_frame, font=("Segoe UI", 10), width=50)
        field_name_entry.pack(fill=X, pady=(0, 16))
        field_name_entry.focus()

        field_value_label = Label(
            main_frame, text="Field Value:", bg="#ffffff", font=("Segoe UI", 11, "bold"), fg="#333333"
        )
        field_value_label.pack(anchor=W, pady=(0, 8))

        field_value_entry = ttk.Entry(main_frame, font=("Segoe UI", 10), width=50)
        field_value_entry.pack(fill=X, pady=(0, 12))

        example_label = Label(
            main_frame,
            text="Examples: GPS Latitude: 40.7128 | Camera Model: Canon EOS | Author: John Doe",
            bg="#ffffff",
            font=("Segoe UI", 9, "italic"),
            fg="#999999",
            wraplength=500,
            justify=LEFT,
        )
        example_label.pack(anchor=W, pady=(0, 20))

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

            if field_name in self.app.editor_entry_fields:
                messagebox.showwarning(
                    "Duplicate Field", f"Field '{field_name}' already exists. Edit it directly or use a different name."
                )
                field_name_entry.focus()
                return

            self.app.extracted_metadata[field_name] = field_value
            self.populate_editor_fields(self.app.extracted_metadata)

            if self.app.editor_status:
                self.app.editor_status.config(text=f"Added new field: {field_name}", fg="#28a745")

            dialog.destroy()
            messagebox.showinfo("Success", f"Field '{field_name}' added successfully.\n\nDon't forget to save your changes.")

        def cancel_dialog():
            dialog.destroy()

        ttk.Button(button_frame, text="Add", command=add_field).pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_dialog).pack(side=LEFT, padx=5)
        field_value_entry.bind("<Return>", lambda e: add_field())
