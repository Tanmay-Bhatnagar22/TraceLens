"""Preview tab module for TraceLens GUI.

Handles report generation, PDF rendering/previewing, zoom controls, saving, and printing.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from tkinter import (
    BOTH,
    CENTER,
    DISABLED,
    END,
    FLAT,
    LEFT,
    NORMAL,
    RIGHT,
    SOLID,
    W,
    WORD,
    X,
    Y,
    Button,
    Canvas,
    Frame,
    Label,
    messagebox,
    scrolledtext,
    ttk,
)
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.gui.gui import MetadataAnalyzerApp

# Try importing reports module
try:
    from src.core.reports import report
except ImportError:  # pragma: no cover - optional dependency
    report = None

# Try importing risk analyzer module
try:
    from src.core.risk import risk_analyzer
except ImportError:  # pragma: no cover - optional dependency
    risk_analyzer = None

from src.config.logging_config import get_logger

logger = get_logger("gui.preview")


class PreviewTab:
    """Component managing the Report Preview tab UI, PDF rendering, and zoom operations."""

    def __init__(self, parent_frame: Frame, app: MetadataAnalyzerApp) -> None:
        self.parent = parent_frame
        self.app = app
        self.build_ui()

    def build_ui(self) -> None:
        """Construct the Preview tab UI widgets."""
        report_container = Frame(self.parent, bg="#ffffff")
        report_container.pack(fill=BOTH, expand=True)

        preview_frame = Frame(report_container, bg="#e8e8e8")
        preview_frame.pack(side=LEFT, fill=BOTH, expand=True)
        preview_label = Label(
            preview_frame, text="Report Preview", bg="#e8e8e8", font=("Segoe UI", 12, "bold"), fg="#1a1a1a"
        )
        preview_label.pack(anchor=W, padx=12, pady=(12, 6))

        self.app.report_preview = scrolledtext.ScrolledText(
            preview_frame,
            wrap=WORD,
            bg="#ffffff",
            font=("Segoe UI", 11),
            fg="#333333",
            bd=1,
            relief=SOLID,
            highlightthickness=0,
            pady=12,
            padx=12,
        )
        self.app.report_preview.config(state=DISABLED)

        # Container for canvas and scrollbar
        image_container = Frame(preview_frame, bg="#e8e8e8")
        image_container.pack(fill=BOTH, expand=True, padx=12, pady=(0, 12))

        # Scrollbar for preview canvas
        self.app.preview_scrollbar = ttk.Scrollbar(image_container, orient="vertical")

        # Canvas for scrollable image preview
        self.app.preview_canvas = Canvas(image_container, bg="#e8e8e8", highlightthickness=0, bd=0)
        self.app.preview_canvas.pack(side=LEFT, fill=BOTH, expand=True)

        self.app.preview_scrollbar.config(command=self.app.preview_canvas.yview)
        self.app.preview_canvas.config(yscrollcommand=self.app.preview_scrollbar.set)

        # Label inside canvas for image display
        self.app.report_image_label = Label(
            self.app.preview_canvas,
            bg="#e8e8e8",
            text="No report generated yet.\n\nGenerate a report from the Extractor or Editor tab to see preview.",
            font=("Segoe UI", 11),
            fg="#666666",
            justify=CENTER,
        )
        self.app.canvas_window_id = self.app.preview_canvas.create_window(
            0, 0, window=self.app.report_image_label, anchor="n"
        )

        # Bind canvas configure event to center image when canvas size changes
        self.app.preview_canvas.bind("<Configure>", self.on_canvas_configure)

        def _on_preview_mousewheel(event):
            delta_steps = 0
            if hasattr(event, "delta") and event.delta:
                delta_steps = int(-1 * (event.delta / 120))
            elif getattr(event, "num", None) == 4:
                delta_steps = -1
            elif getattr(event, "num", None) == 5:
                delta_steps = 1
            if delta_steps and self.app.preview_canvas:
                self.app.preview_canvas.yview_scroll(delta_steps, "units")

        self.app.preview_canvas.bind("<MouseWheel>", _on_preview_mousewheel)
        self.app.preview_canvas.bind("<Button-4>", _on_preview_mousewheel)
        self.app.preview_canvas.bind("<Button-5>", _on_preview_mousewheel)
        self.app.report_image_label.bind("<MouseWheel>", _on_preview_mousewheel)
        self.app.report_image_label.bind("<Button-4>", _on_preview_mousewheel)
        self.app.report_image_label.bind("<Button-5>", _on_preview_mousewheel)

        controls_side = Frame(report_container, bg="#f8f9fa", width=220)
        controls_side.pack(side=RIGHT, fill=Y, padx=2, pady=2)
        controls_side.pack_propagate(False)
        Label(controls_side, text="Actions", bg="#f8f9fa", font=("Segoe UI", 11, "bold"), fg="#1a1a1a").pack(
            anchor=W, padx=12, pady=(12, 6)
        )
        Button(
            controls_side,
            text="Save Report",
            command=self.save_report_from_preview,
            bg="#007acc",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief=FLAT,
            cursor="hand2",
            pady=8,
        ).pack(fill=X, padx=12, pady=6)
        Button(
            controls_side,
            text="Print Report",
            command=self.print_report_from_preview,
            bg="#28a745",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief=FLAT,
            cursor="hand2",
            pady=8,
        ).pack(fill=X, padx=12, pady=6)

        Label(controls_side, text="Zoom", bg="#f8f9fa", font=("Segoe UI", 11, "bold"), fg="#1a1a1a").pack(
            anchor=W, padx=12, pady=(24, 6)
        )
        zoom_frame = Frame(controls_side, bg="#f8f9fa")
        zoom_frame.pack(fill=X, padx=12, pady=6)
        Button(
            zoom_frame,
            text="+",
            command=self.zoom_in_image,
            bg="#007acc",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief=FLAT,
            cursor="hand2",
            width=3,
        ).pack(side=LEFT, padx=(0, 6))
        Button(
            zoom_frame,
            text="−",
            command=self.zoom_out_image,
            bg="#007acc",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief=FLAT,
            cursor="hand2",
            width=3,
        ).pack(side=LEFT, padx=(0, 6))
        Button(
            zoom_frame,
            text="Reset",
            command=self.reset_zoom_image,
            bg="#6c757d",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief=FLAT,
            cursor="hand2",
            width=5,
        ).pack(side=LEFT)
        self.app.zoom_display_label = Label(
            controls_side, text="100%", bg="#f8f9fa", font=("Segoe UI", 10), fg="#333333"
        )
        self.app.zoom_display_label.pack(anchor=W, padx=12, pady=(6, 0))

    def generate_report(self) -> None:
        """Generate a metadata report and display in preview tab."""
        if not self.app.extracted_metadata or not self.app.file_path:
            messagebox.showwarning("No Data", "Please extract metadata first before generating a report.")
            return
        if not report:
            logger.error("Report generation failed: Reports module not available")
            messagebox.showerror("Error", "Reports module not available.")
            return
        try:
            logger.info("Generating report for: '%s'", os.path.basename(self.app.file_path))
            if risk_analyzer and isinstance(self.app.extracted_metadata, dict):
                self.app.risk_analysis = risk_analyzer.analyze_metadata(
                    self.app.extracted_metadata,
                    self.app.file_path,
                    fallback_timestamps=self.app._get_timeline_fallbacks(
                        extracted_at=datetime.now().isoformat(sep=" ", timespec="seconds")
                    ),
                )
            metadata_text = report.generate_report_text(
                self.app.extracted_metadata,
                self.app.file_path,
                risk_analysis=self.app.risk_analysis,
                batch_summary=self.app.risk_batch_summary,
            )
            self.update_report_preview(metadata_text)
            logger.info("Generated report preview for '%s' (%d characters)", os.path.basename(self.app.file_path), len(metadata_text))
            self.app.set_status("Report preview ready")
        except Exception as e:
            logger.error("Failed to generate report for '%s': %s", os.path.basename(self.app.file_path or "file"), e)
            self.app.set_status(f"Report generation error: {str(e)}")
            messagebox.showerror("Report Error", f"Failed to generate report: {str(e)}")

    def update_report_preview(self, text: str) -> None:
        """Update the report preview panel with formatted text / rendered PDF image."""
        self.app.report_last_text = text or ""

        def _show_text_preview():
            try:
                if self.app.preview_scrollbar and self.app.preview_scrollbar.winfo_exists():
                    self.app.preview_scrollbar.pack_forget()
            except Exception:
                pass

            try:
                if self.app.report_preview and self.app.report_preview.winfo_exists():
                    self.app.report_preview.pack(fill=BOTH, expand=True)
                    self.app.report_preview.config(state=NORMAL)
                    self.app.report_preview.delete(1.0, END)
                    self.app.report_preview.insert(END, self.app.report_last_text)
                    self.app.report_preview.config(state=DISABLED)
            except Exception as e:  # pragma: no cover - UI fallback
                print(f"Error showing text preview: {e}")

        def _show_image_preview(pil_img):
            try:
                try:
                    from PIL import Image, ImageTk
                except ImportError:
                    _show_text_preview()
                    return

                self.app.preview_base_image = pil_img
                self.app.preview_image_zoom = 1.0

                max_width = self.app.window_width - 280 if self.app.window_width else 900

                img_width, img_height = pil_img.size
                width_ratio = max_width / img_width
                scale_ratio = min(width_ratio, 1.0)

                if scale_ratio < 1.0:
                    new_width = int(img_width * scale_ratio)
                    new_height = int(img_height * scale_ratio)
                    pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    img_width, img_height = new_width, new_height

                self.app.report_preview_tk_img = ImageTk.PhotoImage(pil_img)

                if self.app.report_preview and self.app.report_preview.winfo_exists():
                    self.app.report_preview.pack_forget()

                if self.app.report_image_label and self.app.report_image_label.winfo_exists():
                    self.app.report_image_label.config(image=self.app.report_preview_tk_img, bg="#e8e8e8")

                if self.app.preview_canvas and self.app.preview_canvas.winfo_exists():
                    self.app.preview_canvas.update_idletasks()
                    canvas_width = self.app.preview_canvas.winfo_width()
                    canvas_height = self.app.preview_canvas.winfo_height()

                    self.app.preview_canvas.coords(self.app.canvas_window_id, canvas_width // 2, 10)
                    self.app.preview_canvas.config(scrollregion=self.app.preview_canvas.bbox("all"))
                    if (
                        img_height > canvas_height
                        and self.app.preview_scrollbar
                        and self.app.preview_scrollbar.winfo_exists()
                    ):
                        self.app.preview_scrollbar.pack(side=RIGHT, fill=Y)
                    else:
                        if self.app.preview_scrollbar and self.app.preview_scrollbar.winfo_exists():
                            self.app.preview_scrollbar.pack_forget()

                if hasattr(self.app, "zoom_display_label") and self.app.zoom_display_label:
                    self.app.zoom_display_label.config(text="100%")

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
            if not report:
                return False
            try:
                temp_dir = tempfile.gettempdir()
                temp_pdf = os.path.join(temp_dir, f"metadata_report_preview_{os.getpid()}.pdf")
                report.create_pdf_report_from_text(self.app.report_last_text, temp_pdf)
                return _try_render_image_from_pdf(temp_pdf)
            except Exception as e:  # pragma: no cover - UI fallback
                print(f"Error creating preview PDF: {e}")
                return False

        if not _render_image_preview():
            _show_text_preview()

        try:
            if self.app.nb_widget is not None and self.app.tab4_ref is not None:
                self.app.nb_widget.select(self.app.tab4_ref)
        except Exception:
            pass

    def save_report_from_preview(self) -> None:
        """Save the current report preview to a PDF file."""
        if not report:
            logger.error("Reports module not available for saving")
            messagebox.showerror("Error", "Reports module not available.")
            return
        try:
            if not self.app.report_last_text.strip():
                messagebox.showwarning("No Data", "There is no report content to save.")
                return
            logger.info("Exporting report preview for '%s' to PDF...", os.path.basename(self.app.file_path or "file"))
            report.save_metadata(self.app.report_last_text)
            logger.info("Report export dialog completed")
        except Exception as e:
            logger.error("Failed to save report: %s", e)
            messagebox.showerror("Save Error", f"Failed to save report: {str(e)}")

    def print_report_from_preview(self) -> None:
        """Send the current report preview to the default printer."""
        if not report:
            logger.error("Reports module not available for printing")
            messagebox.showerror("Error", "Reports module not available.")
            return
        try:
            if not self.app.report_last_text.strip():
                messagebox.showwarning("No Data", "There is no report content to print.")
                return
            logger.info("Sending report for '%s' to printer...", os.path.basename(self.app.file_path or "file"))
            report.print_metadata_report(self.app.report_last_text)
            logger.info("Print job sent to system spooler")
        except Exception as e:
            logger.error("Failed to print report: %s", e)
            messagebox.showerror("Print Error", f"Failed to print report: {str(e)}")

    def on_canvas_configure(self, event=None) -> None:
        """Center the image in canvas when canvas is configured/resized."""
        try:
            if self.app.preview_canvas and self.app.preview_canvas.winfo_exists():
                canvas_width = self.app.preview_canvas.winfo_width()
                canvas_height = self.app.preview_canvas.winfo_height()

                if canvas_width > 1 and canvas_height > 1:
                    self.app.preview_canvas.coords(self.app.canvas_window_id, canvas_width // 2, 10)
                    self.app.preview_canvas.config(scrollregion=self.app.preview_canvas.bbox("all"))
                    if self.app.report_image_label and self.app.report_image_label.winfo_exists():
                        label_height = self.app.report_image_label.winfo_height()
                        if (
                            label_height > canvas_height
                            and self.app.preview_scrollbar
                            and self.app.preview_scrollbar.winfo_exists()
                        ):
                            self.app.preview_scrollbar.pack(side=RIGHT, fill=Y)
                        elif self.app.preview_scrollbar and self.app.preview_scrollbar.winfo_exists():
                            self.app.preview_scrollbar.pack_forget()
        except Exception:
            pass

    def zoom_in_image(self) -> None:
        """Zoom in on the preview image by 20%."""
        if self.app.preview_base_image is None:
            return
        self.app.preview_image_zoom = min(self.app.preview_image_zoom + 0.2, 2.0)
        self.apply_image_zoom()

    def zoom_out_image(self) -> None:
        """Zoom out on the preview image by 20%."""
        if self.app.preview_base_image is None:
            return
        self.app.preview_image_zoom = max(self.app.preview_image_zoom - 0.2, 0.4)
        self.apply_image_zoom()

    def reset_zoom_image(self) -> None:
        """Reset image zoom to 100%."""
        if self.app.preview_base_image is None:
            return
        self.app.preview_image_zoom = 1.0
        self.apply_image_zoom()

    def apply_image_zoom(self) -> None:
        """Apply the current zoom level to the preview image."""
        try:
            from PIL import Image, ImageTk

            if self.app.preview_base_image is None:
                return

            max_width = self.app.window_width - 280 if self.app.window_width else 900

            img_width, img_height = self.app.preview_base_image.size
            width_ratio = max_width / img_width
            base_scale_ratio = min(width_ratio, 1.0)

            final_scale = base_scale_ratio * self.app.preview_image_zoom
            new_width = int(img_width * final_scale)
            new_height = int(img_height * final_scale)

            resized_img = self.app.preview_base_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.app.report_preview_tk_img = ImageTk.PhotoImage(resized_img)

            if self.app.report_image_label and self.app.report_image_label.winfo_exists():
                self.app.report_image_label.config(image=self.app.report_preview_tk_img)

            if self.app.preview_canvas and self.app.preview_canvas.winfo_exists():
                self.app.preview_canvas.update_idletasks()
                canvas_width = self.app.preview_canvas.winfo_width()
                canvas_height = self.app.preview_canvas.winfo_height()

                x_center = canvas_width // 2
                y_center = 10
                self.app.preview_canvas.coords(self.app.canvas_window_id, x_center, y_center)

                scroll_width = max(canvas_width, new_width)
                scroll_height = max(canvas_height, new_height)
                self.app.preview_canvas.config(scrollregion=(0, 0, scroll_width, scroll_height))

                if (
                    new_height > canvas_height
                    and self.app.preview_scrollbar
                    and self.app.preview_scrollbar.winfo_exists()
                ):
                    self.app.preview_scrollbar.pack(side=RIGHT, fill=Y)
                elif self.app.preview_scrollbar and self.app.preview_scrollbar.winfo_exists():
                    self.app.preview_scrollbar.pack_forget()

            if hasattr(self.app, "zoom_display_label") and self.app.zoom_display_label:
                self.app.zoom_display_label.config(text=f"{int(self.app.preview_image_zoom * 100)}%")

            self.app.set_status(f"Image zoom: {int(self.app.preview_image_zoom * 100)}%")

        except Exception as e:
            print(f"Error applying image zoom: {e}")
