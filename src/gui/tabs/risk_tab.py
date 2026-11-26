"""Risk analyzer tab module for TraceLens GUI.

Handles privacy risk gauge visualization, forensic timeline plotting, and anomaly reporting.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from tkinter import (
    BOTH,
    DISABLED,
    END,
    FLAT,
    NORMAL,
    SOLID,
    W,
    WORD,
    Frame,
    Label,
    messagebox,
    scrolledtext,
)
from typing import TYPE_CHECKING, Any

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

if TYPE_CHECKING:
    from src.gui.gui import MetadataAnalyzerApp

# Try importing risk analyzer module
try:
    from src.core.risk import risk_analyzer
except ImportError:  # pragma: no cover - optional dependency
    risk_analyzer = None

# Try importing extractor module
try:
    from src.core.extractor import extractor
except ImportError:  # pragma: no cover - optional dependency
    extractor = None

from src.config.logging_config import get_logger

logger = get_logger("gui.risk")


class RiskTab:
    """Component managing the Risk Analyzer tab UI and forensic visualizations."""

    def __init__(self, parent_frame: Frame, app: MetadataAnalyzerApp) -> None:
        self.parent = parent_frame
        self.app = app
        self.build_ui()

    def build_ui(self) -> None:
        """Construct the Risk Analyzer tab UI widgets."""
        container = Frame(self.parent, bg="#ffffff", relief=SOLID, bd=1)
        container.pack(fill=BOTH, expand=True, padx=8, pady=8)

        container.columnconfigure(0, weight=3)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        # ---------------- LEFT PANEL ----------------
        left_panel = Frame(container, bg="#ffffff")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 8), pady=10)

        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=1)
        left_panel.rowconfigure(3, weight=2)

        Label(
            left_panel,
            text="Risk Meter",
            bg="#ffffff",
            font=("Segoe UI", 11, "bold"),
            fg="#1a1a1a",
            anchor=W,
        ).grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 4))

        risk_meter_frame = Frame(left_panel, bg="#ffffff", relief=SOLID, bd=1)
        risk_meter_frame.grid(row=1, column=0, sticky="nsew")

        Label(
            left_panel,
            text="Forensic Timeline",
            bg="#ffffff",
            font=("Segoe UI", 11, "bold"),
            fg="#1a1a1a",
            anchor=W,
        ).grid(row=2, column=0, sticky="ew", padx=2, pady=(12, 4))

        timeline_frame = Frame(left_panel, bg="#ffffff", relief=SOLID, bd=1)
        timeline_frame.grid(row=3, column=0, sticky="nsew")

        # ---------------- RIGHT PANEL ----------------
        right_column = Frame(container, bg="#ffffff")
        right_column.grid(row=0, column=1, sticky="nsew", padx=(8, 10), pady=10)

        right_column.columnconfigure(0, weight=1)
        right_column.rowconfigure(1, weight=1)

        Label(
            right_column,
            text="Comments",
            bg="#ffffff",
            font=("Segoe UI", 11, "bold"),
            fg="#1a1a1a",
            anchor=W,
        ).grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 4))

        comments_frame = Frame(right_column, bg="#ffffff", relief=SOLID, bd=1)
        comments_frame.grid(row=1, column=0, sticky="nsew")

        # ---------------- RISK CHART ----------------
        self.app.risk_chart_canvas = FigureCanvasTkAgg(
            Figure(figsize=(6.0, 2.4), facecolor="white"), master=risk_meter_frame
        )
        self.app.risk_chart_canvas.get_tk_widget().pack(fill=BOTH, expand=True, padx=8, pady=8)

        # ---------------- TIMELINE CHART ----------------
        self.app.timeline_chart_canvas = FigureCanvasTkAgg(
            Figure(figsize=(6.0, 2.6), facecolor="white"), master=timeline_frame
        )
        self.app.timeline_chart_canvas.get_tk_widget().pack(fill=BOTH, expand=True, padx=8, pady=8)

        # ---------------- COMMENTS ----------------
        self.app.risk_summary_text = scrolledtext.ScrolledText(
            comments_frame,
            wrap=WORD,
            bg="#f5f5f5",
            font=("Segoe UI", 10),
            fg="#333333",
            bd=0,
            relief=FLAT,
            padx=10,
            pady=10,
        )
        self.app.risk_summary_text.pack(fill=BOTH, expand=True)
        self.app.risk_summary_text.config(state=DISABLED)

        self.parent.after_idle(lambda: self.render_risk_analysis(None))

    def render_risk_analysis(self, analysis: dict | None) -> None:
        """Render risk gauge, reasons and timeline chart in Risk analyzer tab."""
        if self.app.risk_summary_text and self.app.risk_summary_text.winfo_exists():
            self.app.risk_summary_text.config(state=NORMAL)
            self.app.risk_summary_text.delete(1.0, END)

        if not analysis:
            if self.app.risk_chart_canvas:
                fig = self.app.risk_chart_canvas.figure
                fig.clear()
                ax = fig.add_subplot(111)

                risk_color = "#3498db"
                full_fill = plt.matplotlib.patches.Wedge(
                    (0, 0), 1.0, 0, 180, width=1.0, facecolor=risk_color, edgecolor="none", alpha=0.85, zorder=2
                )
                ax.add_patch(full_fill)

                outline = plt.matplotlib.patches.Wedge(
                    (0, 0), 1.0, 0, 180, width=0.04, facecolor="none", edgecolor="#9ca3af", zorder=3
                )
                ax.add_patch(outline)
                ax.plot([1, -1], [0, 0], color="#9ca3af", linewidth=2, zorder=3)

                ax.text(0, 0.35, "0%", ha="center", va="center", fontsize=30, weight="bold", color="#1f2937")
                ax.text(0, 0.10, "Risk: N/A", ha="center", va="center", fontsize=12, color="#4b5563")
                ax.set_title("Privacy Risk Gauge", fontsize=11, weight="bold", y=0.95, pad=2)
                ax.set_xlim(-1.25, 1.25)
                ax.set_ylim(-0.25, 1.25)
                ax.axis("off")
                fig.tight_layout(pad=0.5)
                self.app.risk_chart_canvas.draw_idle()

            if self.app.timeline_chart_canvas:
                fig = self.app.timeline_chart_canvas.figure
                fig.clear()
                ax = fig.add_subplot(111)
                ax.axis("off")
                ax.text(0.5, 0.5, "No timeline events discovered from metadata.", ha="center", va="center", fontsize=10)
                fig.tight_layout(pad=0.5)
                self.app.timeline_chart_canvas.draw_idle()

            if self.app.risk_summary_text and self.app.risk_summary_text.winfo_exists():
                self.app.risk_summary_text.insert(
                    END, "Risk Level: N/A\nRisk Score: N/A\n\nRun extraction to view risk reasons and forensic timeline."
                )
                self.app.risk_summary_text.config(state=DISABLED)
            return

        score = int(analysis.get("risk_score", 0))
        level = analysis.get("risk_level", "LOW")
        reasons = analysis.get("reasons", [])
        timeline = analysis.get("timeline", [])
        anomalies = analysis.get("anomalies", [])

        if self.app.risk_chart_canvas:
            fig = Figure(figsize=(6.0, 2.4), facecolor="white")
            ax = fig.add_subplot(111)
            color_map = {"LOW": "#2ecc71", "MEDIUM": "#f39c12", "HIGH": "#e74c3c"}
            risk_color = color_map.get(level, "#3498db")

            full_fill = plt.matplotlib.patches.Wedge(
                (0, 0), 1.0, 0, 180, width=1.0, facecolor=risk_color, edgecolor="none", alpha=0.85, zorder=2
            )
            ax.add_patch(full_fill)

            outline = plt.matplotlib.patches.Wedge(
                (0, 0), 1.0, 0, 180, width=0.04, facecolor="none", edgecolor="#9ca3af", zorder=3
            )
            ax.add_patch(outline)
            ax.plot([1, -1], [0, 0], color="#9ca3af", linewidth=2, zorder=3)

            ax.text(0, 0.35, f"{score}%", ha="center", va="center", fontsize=30, weight="bold", color="#1f2937")
            ax.text(0, 0.10, f"Risk: {level}", ha="center", va="center", fontsize=12, color="#4b5563")

            ax.set_title("Privacy Risk Gauge", fontsize=11, weight="bold", y=0.95, pad=2)
            ax.set_xlim(-1.25, 1.25)
            ax.set_ylim(-0.25, 1.25)
            ax.axis("off")
            self.app.risk_chart_canvas.figure = fig
            self.app.risk_chart_canvas.draw()

        if self.app.timeline_chart_canvas:
            fig = Figure(figsize=(6.0, 2.6), facecolor="white")
            ax = fig.add_subplot(111)
            if timeline:
                events_with_dates = []
                for event in timeline:
                    try:
                        ts_str = event.get("timestamp", "")
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
                    date_events = defaultdict(list)
                    for dt, event_name in events_with_dates:
                        date_key = dt.date()
                        date_events[date_key].append(event_name)

                    sorted_dates = sorted(date_events.keys())
                    y_vals = [0.5] * len(sorted_dates)

                    event_labels = []
                    for d in sorted_dates:
                        events = date_events[d]
                        label = events[0] if events else ""
                        label = label.replace("_", " ").title()
                        if "create" in label.lower():
                            label = "Creation"
                        elif "modif" in label.lower():
                            label = "Modification"
                        elif "extract" in label.lower():
                            label = "Extraction"
                        event_labels.append(label)

                    full_date_labels = [d.strftime("%Y-%m-%d") for d in sorted_dates]
                    x_vals = list(range(len(sorted_dates)))

                    ax.fill_between(x_vals, y_vals, alpha=0.4, color="#ffffffe6", zorder=1)
                    ax.plot(x_vals, y_vals, color="#4facfe", linewidth=2.5, marker="o", markersize=8, zorder=2)

                    for x, y, full_date, event_label in zip(x_vals, y_vals, full_date_labels, event_labels):
                        ax.text(x, y + 0.2, full_date, ha="center", va="bottom", fontsize=8, color="#333333", weight="bold")
                        if event_label:
                            ax.text(
                                x, y + 0.05, event_label, ha="center", va="bottom", fontsize=7, color="#666666", style="italic"
                            )

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
            self.app.timeline_chart_canvas.figure = fig
            self.app.timeline_chart_canvas.draw()

        if self.app.risk_summary_text and self.app.risk_summary_text.winfo_exists():
            self.app.risk_summary_text.insert(END, f"Risk Level: {level}\n")
            self.app.risk_summary_text.insert(END, f"Risk Score: {score}/100\n")
            self.app.risk_summary_text.insert(END, f"Timeline Events: {len(timeline)}\n")
            self.app.risk_summary_text.insert(END, f"Anomalies: {len(anomalies)}\n\n")

            self.app.risk_summary_text.insert(END, "Why this risk:\n")
            for reason in reasons:
                self.app.risk_summary_text.insert(END, f"• {reason}\n")

            if self.app.risk_batch_summary:
                counts = self.app.risk_batch_summary.get("risk_counts", {})
                self.app.risk_summary_text.insert(END, "\nBatch Summary:\n")
                self.app.risk_summary_text.insert(END, f"• LOW: {counts.get('LOW', 0)}\n")
                self.app.risk_summary_text.insert(END, f"• MEDIUM: {counts.get('MEDIUM', 0)}\n")
                self.app.risk_summary_text.insert(END, f"• HIGH: {counts.get('HIGH', 0)}\n")

            self.app.risk_summary_text.config(state=DISABLED)

    def open_risk_analyzer_with_scan(self) -> None:
        """Open Risk analyzer tab and scan current file metadata for privacy/forensic risk."""
        if not self.app.file_path:
            messagebox.showwarning("No File Selected", "Please choose a file first.")
            return

        if not risk_analyzer:
            messagebox.showerror("Error", "Risk analyzer module not available.")
            return

        if (
            not self.app.extracted_metadata
            or not isinstance(self.app.extracted_metadata, dict)
            or "Error" in self.app.extracted_metadata
        ):
            if not extractor:
                messagebox.showerror("Error", "Extractor module not available.")
                return
            try:
                self.app.set_status("Extracting metadata for risk scan...")
                if self.app.progress_bar:
                    self.app.progress_bar.start()
                self.app.extracted_metadata, db_row = extractor.extract_and_store(self.app.file_path)
                if self.app.progress_bar:
                    self.app.progress_bar.stop()
                if hasattr(self.app, "_display_extracted_metadata"):
                    self.app._display_extracted_metadata(self.app.extracted_metadata, self.app.file_path, db_row)
                if callable(self.app.history_refresh):
                    self.app.history_refresh()
            except Exception as exc:
                if self.app.progress_bar:
                    self.app.progress_bar.stop()
                messagebox.showerror("Risk Scan Error", f"Failed to extract metadata before risk scan: {exc}")
                return

        try:
            logger.info("Evaluating privacy and forensic risk for: '%s'", os.path.basename(self.app.file_path))
            self.app.risk_analysis = risk_analyzer.analyze_metadata(
                self.app.extracted_metadata,
                self.app.file_path,
                fallback_timestamps=self.app._get_timeline_fallbacks(
                    extracted_at=datetime.now().isoformat(sep=" ", timespec="seconds")
                ),
            )
            self.render_risk_analysis(self.app.risk_analysis)

            if self.app.nb_widget is not None and self.app.tab5_ref is not None:
                self.app.nb_widget.select(self.app.tab5_ref)

            score = self.app.risk_analysis.get("risk_score", 0) if isinstance(self.app.risk_analysis, dict) else 0
            level = self.app.risk_analysis.get("risk_level", "N/A") if isinstance(self.app.risk_analysis, dict) else "N/A"
            logger.info("Risk scan complete for '%s': Score %s/100 (Level: %s)", os.path.basename(self.app.file_path), score, level)
            self.app.set_status(f"Risk scan complete: {level}")
        except Exception as exc:
            logger.error("Risk scan failed for '%s': %s", os.path.basename(self.app.file_path or "file"), exc)
            messagebox.showerror("Risk Scan Error", f"Failed to analyze risk: {exc}")
