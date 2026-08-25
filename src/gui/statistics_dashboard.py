"""Statistical Dashboard module for TraceLens application.

Provides interactive analytics, multi-tab material design metrics, visual charts,
forensic metadata insights, interactive data explorer, storage optimization,
and asynchronous report generation for extracted file records.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
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
    Checkbutton,
    DoubleVar,
    Entry,
    Frame,
    Label,
    Listbox,
    Menu,
    PhotoImage,
    StringVar,
    Tk,
    Toplevel,
    filedialog,
    messagebox,
    scrolledtext,
    ttk,
)

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.database import db

# Try importing risk analyzer module for risk metrics
try:
    from src.core.risk import risk_analyzer
except ImportError:  # pragma: no cover - optional dependency
    risk_analyzer = None


def parse_size_to_bytes(size_str: str | int | float | None) -> int:
    """Convert formatted size string to bytes.

    Args:
        size_str: Formatted size string (e.g. '12.5 KB', '1.2 MB') or numeric value.

    Returns:
        int: Size in bytes.
    """
    if not size_str or size_str == "Unknown":
        return 0
    try:
        parts = str(size_str).strip().split()
        if len(parts) == 2:
            value = float(parts[0])
            unit = parts[1].upper()
            multipliers = {
                "B": 1,
                "KB": 1024,
                "MB": 1024**2,
                "GB": 1024**3,
                "TB": 1024**4,
            }
            return int(value * multipliers.get(unit, 1))
        return int(float(size_str))
    except (ValueError, IndexError, AttributeError):
        return 0


def format_size(bytes_val: float | int) -> str:
    """Format bytes into a human-readable size string.

    Args:
        bytes_val: Size in bytes.

    Returns:
        str: Human-readable size with unit (e.g. '1.5 MB').
    """
    try:
        val = float(bytes_val)
    except (ValueError, TypeError):
        return "0.0 B"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if val < 1024.0 or unit == "TB":
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} TB"


def filter_records(records: list, criteria: dict) -> list:
    """Apply date range, file type, risk level, and search filters to database records.

    Args:
        records: List of database rows/tuples.
        criteria: Dict containing 'date_range', 'file_type', 'risk_level', and 'search'.

    Returns:
        list: Filtered records.
    """
    filtered = list(records)

    # Date filter
    date_range = criteria.get("date_range", "All Time")
    if date_range != "All Time":
        now = datetime.now()
        if date_range == "Today":
            cutoff = datetime(now.year, now.month, now.day)
        elif date_range == "Last 7 Days":
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
    file_type = criteria.get("file_type", "All Types")
    if file_type and file_type not in ("All Types", "All"):
        filtered = [
            r for r in filtered
            if len(r) > 4 and str(r[4]).lower() == str(file_type).lower()
        ]

    # Search filter
    search_term = criteria.get("search", "").lower().strip()
    if search_term:
        filtered = [
            r for r in filtered
            if (len(r) > 2 and search_term in str(r[2]).lower())
            or (len(r) > 1 and search_term in str(r[1]).lower())
            or (len(r) > 4 and search_term in str(r[4]).lower())
        ]

    return filtered


def calculate_enhanced_stats(
    records: list,
    risk_analyzer_module=None,
    risk_cache: dict | None = None,
) -> dict | None:
    """Calculate aggregated metrics, forensic insights, and distribution statistics from records.

    Args:
        records: List of database rows.
        risk_analyzer_module: Optional risk analyzer module (defaults to global risk_analyzer).
        risk_cache: Optional cache dict for risk score lookups.

    Returns:
        dict | None: Dictionary of calculated metrics or None if records is empty.
    """
    total = len(records)
    if total == 0:
        return None

    if risk_analyzer_module is None:
        risk_analyzer_module = risk_analyzer
    if risk_cache is None:
        risk_cache = {}

    stats: dict = {
        "total": total,
        "file_types": {},
        "total_size": 0,
        "file_sizes": [],
        "sizes_by_type": defaultdict(list),
        "dates": [],
        "files_by_date": defaultdict(int),
        "risk_counts": {"LOW": 0, "MEDIUM": 0, "HIGH": 0},
        "record_risk_map": {},
        "metadata_keys": Counter(),
        "authors": Counter(),
        "software": Counter(),
        "completeness_scores": [],
    }

    for record in records:
        rec_id = record[0] if len(record) > 0 else 0
        rec_path = record[1] if len(record) > 1 else ""
        rec_name = record[2] if len(record) > 2 else "Unknown"
        ft = record[4] if len(record) > 4 and record[4] else "Unknown"
        stats["file_types"][ft] = stats["file_types"].get(ft, 0) + 1

        size_bytes = parse_size_to_bytes(record[3]) if len(record) > 3 else 0
        stats["total_size"] += size_bytes
        stats["file_sizes"].append((size_bytes, rec_name, record))
        stats["sizes_by_type"][ft].append(size_bytes)

        if len(record) > 5 and record[5]:
            try:
                date_obj = datetime.fromisoformat(record[5])
                date_key = date_obj.strftime("%Y-%m-%d")
                stats["dates"].append(date_obj)
                stats["files_by_date"][date_key] += 1
            except Exception:
                pass

        parsed_metadata = {}
        if len(record) > 7 and record[7]:
            try:
                parsed_metadata = (
                    json.loads(record[7])
                    if isinstance(record[7], str)
                    else (record[7] or {})
                )
            except Exception:
                parsed_metadata = {}

        field_count = len(parsed_metadata)
        completeness_pct = min(100.0, (field_count / 15.0) * 100.0) if field_count > 0 else 0.0
        stats["completeness_scores"].append(completeness_pct)

        for k, v in parsed_metadata.items():
            stats["metadata_keys"][k] += 1
            k_lower = str(k).lower()
            if any(term in k_lower for term in ["author", "creator", "artist", "by"]):
                if v and str(v).strip():
                    stats["authors"][str(v).strip()] += 1
            if any(term in k_lower for term in ["software", "producer", "application", "tool"]):
                if v and str(v).strip():
                    stats["software"][str(v).strip()] += 1

        risk_level = "LOW"
        if risk_analyzer_module and len(record) > 7 and record[7]:
            try:
                cache_key = (
                    record[0] if len(record) > 0 else None,
                    record[5] if len(record) > 5 else None,
                    record[6] if len(record) > 6 else None,
                )
                cached_level = risk_cache.get(cache_key)
                if cached_level is None:
                    fallback_ctime = None
                    if rec_path and os.path.exists(rec_path):
                        try:
                            fallback_ctime = datetime.fromtimestamp(
                                os.path.getctime(rec_path)
                            ).isoformat(sep=" ", timespec="seconds")
                        except Exception:
                            pass

                    risk_result = risk_analyzer_module.analyze_metadata(
                        parsed_metadata,
                        rec_path,
                        fallback_timestamps={
                            "Created Date": fallback_ctime,
                            "Modified Date": record[6] if len(record) > 6 else None,
                            "Extraction Date": record[5] if len(record) > 5 else None,
                        },
                    )
                    risk_level = risk_result.get("risk_level", "LOW")
                    risk_cache[cache_key] = risk_level
                else:
                    risk_level = cached_level
            except Exception:
                risk_level = "LOW"

        stats["risk_counts"][risk_level] = stats["risk_counts"].get(risk_level, 0) + 1
        stats["record_risk_map"][rec_id] = risk_level

    stats["avg_size"] = stats["total_size"] / total if total > 0 else 0
    stats["max_size"] = (
        (stats["file_sizes"][0][0], stats["file_sizes"][0][1])
        if stats["file_sizes"]
        else (0, "Unknown")
    )
    if stats["file_sizes"]:
        largest_item = max(stats["file_sizes"], key=lambda x: x[0])
        stats["max_size"] = (largest_item[0], largest_item[1])

    non_zero_sizes = [f for f in stats["file_sizes"] if f[0] > 0]
    stats["min_size"] = (
        min(non_zero_sizes, key=lambda x: x[0])[:2]
        if non_zero_sizes
        else (0, "Unknown")
    )

    stats["largest_files"] = [
        (s[0], s[1]) for s in sorted(stats["file_sizes"], key=lambda x: x[0], reverse=True)[:10]
    ]
    stats["avg_size_by_type"] = {
        ft: sum(sizes) / len(sizes) if sizes else 0
        for ft, sizes in stats["sizes_by_type"].items()
    }
    stats["total_size_by_type"] = {
        ft: sum(sizes) for ft, sizes in stats["sizes_by_type"].items()
    }

    name_counter = Counter(r[2] for r in records if len(r) > 2)
    stats["duplicates"] = [
        {"filename": name, "count": count}
        for name, count in name_counter.items()
        if count > 1
    ]

    stats["avg_completeness"] = (
        sum(stats["completeness_scores"]) / len(stats["completeness_scores"])
        if stats["completeness_scores"]
        else 0.0
    )

    top_ft = max(stats["file_types"].items(), key=lambda x: x[1])[0] if stats["file_types"] else "N/A"
    high_risk_n = stats["risk_counts"].get("HIGH", 0)
    stats["executive_summary"] = (
        f"TraceLens indexed {total} file records across {len(stats['file_types'])} unique formats, "
        f"occupying {format_size(stats['total_size'])} of analyzed storage. The primary file format is '{top_ft.upper()}' "
        f"with {stats['file_types'].get(top_ft, 0)} files. Overall metadata completeness is rated at "
        f"{stats['avg_completeness']:.1f}%. "
        f"{high_risk_n} file{'s have' if high_risk_n != 1 else ' has'} been flagged for HIGH privacy risk requiring remediation."
    )

    return stats


def create_metric_card(
    parent,
    title: str,
    value: str,
    subtitle: str = "",
    bg_start: str = "#667eea",
    bg_end: str = "#764ba2",
    width: int | None = None,
    badge: str | None = None,
) -> Frame:
    """Create an enhanced material design card with gradient simulation and hover effects.

    Args:
        parent: Parent widget.
        title: Card title/metric name.
        value: Main value to display.
        subtitle: Optional subtitle text.
        bg_start: Gradient start / primary background color.
        bg_end: Hover state background color.
        width: Optional fixed width.
        badge: Optional badge tag text (e.g. '+12%', 'CRITICAL').

    Returns:
        Frame: The created card container frame.
    """
    card_container = Frame(parent, bg="#dcdfe6", highlightthickness=0)
    if width:
        card_container.config(width=width)

    card = Frame(card_container, bg=bg_start, highlightthickness=0)
    card.pack(padx=2, pady=2, fill=BOTH, expand=True)

    content_frame = Frame(card, bg=bg_start)
    content_frame.pack(fill=BOTH, expand=True, padx=16, pady=14)

    header_row = Frame(content_frame, bg=bg_start)
    header_row.pack(fill=X, pady=(0, 6))

    title_label = Label(
        header_row,
        text=title.upper(),
        font=("Segoe UI", 9, "bold"),
        bg=bg_start,
        fg="#ffffff",
        anchor=W,
    )
    title_label.pack(side=LEFT, fill=X, expand=True)

    badge_label = None
    if badge:
        badge_label = Label(
            header_row,
            text=f" {badge} ",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg=bg_start,
            relief=FLAT,
        )
        badge_label.pack(side=RIGHT)

    value_label = Label(
        content_frame,
        text=value,
        font=("Segoe UI", 22, "bold"),
        bg=bg_start,
        fg="#ffffff",
        anchor=W,
    )
    value_label.pack(fill=X, pady=(0, 4))

    subtitle_label = None
    if subtitle:
        subtitle_label = Label(
            content_frame,
            text=subtitle,
            font=("Segoe UI", 9),
            bg=bg_start,
            fg="#e8ecf4",
            anchor=W,
        )
        subtitle_label.pack(fill=X)

    interactive_widgets = [card_container, card, content_frame, header_row, title_label, value_label]
    if subtitle_label:
        interactive_widgets.append(subtitle_label)

    def on_enter(e):
        card.config(bg=bg_end)
        content_frame.config(bg=bg_end)
        header_row.config(bg=bg_end)
        title_label.config(bg=bg_end)
        value_label.config(bg=bg_end)
        if subtitle_label:
            subtitle_label.config(bg=bg_end)

    def on_leave(e):
        card.config(bg=bg_start)
        content_frame.config(bg=bg_start)
        header_row.config(bg=bg_start)
        title_label.config(bg=bg_start)
        value_label.config(bg=bg_start)
        if subtitle_label:
            subtitle_label.config(bg=bg_start)

    for widget in interactive_widgets:
        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Leave>", on_leave, add="+")

    return card_container


class StatisticsDashboard:
    """Advanced Statistical Analyzer Window for TraceLens.

    Provides a multi-tab desktop analytics suite with:
    - Overview & KPI Summary
    - Interactive Matplotlib Charts & Breakdown
    - Forensic & Metadata Completeness Insights
    - Full-featured Sortable Data Explorer
    - Storage Optimization Recommendations
    - Multi-format Export & Reporting Center
    """

    CHART_PALETTES = {
        "modern": ["#667eea", "#764ba2", "#4facfe", "#00f2fe", "#43e97b", "#fa709a", "#fee140", "#30cfd0"],
        "midnight": ["#2b5876", "#4e4376", "#1e3c72", "#2a5298", "#00b4db", "#0083b0", "#8e2de2", "#4a00e0"],
    }

    def __init__(self, parent=None, database=None, risk_analyzer_instance=None) -> None:
        """Initialize Statistics Dashboard.

        Args:
            parent: Parent Tkinter widget / root window.
            database: Optional database instance (defaults to src.core.database.db).
            risk_analyzer_instance: Optional risk analyzer module/instance.
        """
        self.parent = parent
        self.db = database if database is not None else db
        self.risk_analyzer = (
            risk_analyzer_instance if risk_analyzer_instance is not None else risk_analyzer
        )

        self.window: Toplevel | None = None
        self.notebook: ttk.Notebook | None = None
        self.status_var: StringVar | None = None
        self.refresh_btn: Button | None = None
        self.type_combo: ttk.Combobox | None = None
        self.risk_combo: ttk.Combobox | None = None
        self.search_entry: ttk.Entry | None = None

        # Tab references
        self.tab_overview: dict | None = None
        self.tab_charts: dict | None = None
        self.tab_insights: dict | None = None
        self.tab_optimizer: dict | None = None
        self.tab_reports: dict | None = None
        self._hovered_canvas: Canvas | None = None

        # Charts state
        self.chart_canvas: FigureCanvasTkAgg | None = None
        self.active_figure: Figure | None = None
        self.chart_theme = "modern"

        # Dimensions & state
        self.window_w = 1100
        self.window_h = 760

        self.filter_vars = {}
        self.dashboard_state = {
            "refresh_after_id": None,
            "request_token": 0,
            "records_cache": None,
            "risk_cache": {},
            "filtered_records": [],
            "stats": None,
        }

    def show(self) -> Toplevel:
        """Create and display the Statistics Dashboard window."""
        self.window = Toplevel(self.parent) if self.parent else Toplevel()
        self.window.title("TraceLens — Statistical Analyzer & Forensic Intelligence Suite")
        self.window.config(bg="#f5f7fa")

        # Responsive window sizing (80% of screen size, centered)
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        self.window_w = max(1020, int(screen_width * 0.80))
        self.window_h = max(700, int(screen_height * 0.80))
        x = (screen_width - self.window_w) // 2
        y = (screen_height - self.window_h) // 2
        self.window.geometry(f"{self.window_w}x{self.window_h}+{x}+{y}")
        self.window.minsize(960, 640)

        if self.parent:
            self.window.transient(self.parent)

        self.filter_vars = {
            "date_range": StringVar(value="All Time"),
            "file_type": StringVar(value="All Types"),
            "risk_level": StringVar(value="All Risks"),
            "search": StringVar(value=""),
            "auto_refresh": BooleanVar(value=False),
        }
        self.status_var = StringVar(value="Initializing Statistical Suite...")

        self._configure_styles()
        self._build_ui()
        self.schedule_refresh(force_fetch=True)
        return self.window

    def _configure_styles(self) -> None:
        """Configure ttk theme and styles for professional modern aesthetics."""
        style = ttk.Style()
        style.theme_use("clam")

        # Notebook tab styling matching gui.py
        style.configure("TNotebook", background="#f5f7fa", borderwidth=0)
        style.configure("TNotebook.Tab", padding=[20, 10], font=("Segoe UI", 10))

        # Treeview styling
        style.configure(
            "Stats.Treeview",
            font=("Segoe UI", 9),
            rowheight=28,
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground="#2c3e50",
            borderwidth=0,
        )
        style.configure(
            "Stats.Treeview.Heading",
            font=("Segoe UI", 9, "bold"),
            background="#f0f2f5",
            foreground="#1a252f",
            relief=FLAT,
        )
        style.map("Stats.Treeview", background=[("selected", "#667eea")], foreground=[("selected", "#ffffff")])

    def _build_ui(self) -> None:
        """Construct the complete multi-tab dashboard layout."""
        # ---------------- 1. Top Header Banner ----------------
        header_frame = Frame(self.window, bg="#1e293b", height=75)
        header_frame.pack(fill=X)
        header_frame.pack_propagate(False)

        header_content = Frame(header_frame, bg="#1e293b")
        header_content.pack(fill=BOTH, expand=True, padx=20, pady=10)

        title_box = Frame(header_content, bg="#1e293b")
        title_box.pack(side=LEFT, fill=Y)

        Label(
            title_box,
            text="TraceLens Statistical Analyzer",
            font=("Segoe UI", 16, "bold"),
            bg="#1e293b",
            fg="#ffffff",
            anchor=W,
        ).pack(fill=X)

        Label(
            title_box,
            text="Real-time Forensic Analytics • Metadata Intelligence • Storage Optimization",
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#94a3b8",
            anchor=W,
        ).pack(fill=X)

        header_controls = Frame(header_content, bg="#1e293b")
        header_controls.pack(side=RIGHT, fill=Y)

        self.refresh_btn = Button(
            header_controls,
            text="Refresh Analytics",
            command=lambda: self.schedule_refresh(force_fetch=True),
            bg="#667eea",
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief=FLAT,
            cursor="hand2",
            padx=14,
            pady=6,
            activebackground="#5a67d8",
            activeforeground="#ffffff",
        )
        self.refresh_btn.pack(side=RIGHT, padx=(8, 0), pady=6)

        auto_check = ttk.Checkbutton(
            header_controls,
            text="Auto-refresh (30s)",
            variable=self.filter_vars["auto_refresh"],
            command=self._toggle_auto_refresh,
        )
        auto_check.pack(side=RIGHT, padx=12, pady=8)

        # ---------------- 2. Global Filter & Search Bar ----------------
        filter_bar = Frame(self.window, bg="#ffffff", height=54, highlightbackground="#e2e8f0", highlightthickness=1)
        filter_bar.pack(fill=X, padx=14, pady=(10, 8))
        filter_bar.pack_propagate(False)

        fb_content = Frame(filter_bar, bg="#ffffff")
        fb_content.pack(fill=BOTH, expand=True, padx=12, pady=8)

        # Date Range Filter
        Label(fb_content, text="Period:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#475569").pack(
            side=LEFT, padx=(0, 4)
        )
        date_combo = ttk.Combobox(
            fb_content,
            textvariable=self.filter_vars["date_range"],
            values=["All Time", "Today", "Last 7 Days", "Last 30 Days", "Last 90 Days", "This Year"],
            state="readonly",
            width=13,
            font=("Segoe UI", 9),
        )
        date_combo.pack(side=LEFT, padx=(0, 14))
        date_combo.bind("<<ComboboxSelected>>", lambda e: self.schedule_refresh())

        # File Type Filter
        Label(fb_content, text="Format:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#475569").pack(
            side=LEFT, padx=(0, 4)
        )
        self.type_combo = ttk.Combobox(
            fb_content,
            textvariable=self.filter_vars["file_type"],
            state="readonly",
            width=13,
            font=("Segoe UI", 9),
        )
        self.type_combo.pack(side=LEFT, padx=(0, 14))
        self.type_combo.bind("<<ComboboxSelected>>", lambda e: self.schedule_refresh())

        # Risk Filter
        Label(fb_content, text="Risk:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#475569").pack(
            side=LEFT, padx=(0, 4)
        )
        self.risk_combo = ttk.Combobox(
            fb_content,
            textvariable=self.filter_vars["risk_level"],
            values=["All Risks", "HIGH Risk", "MEDIUM Risk", "LOW Risk"],
            state="readonly",
            width=12,
            font=("Segoe UI", 9),
        )
        self.risk_combo.pack(side=LEFT, padx=(0, 14))
        self.risk_combo.bind("<<ComboboxSelected>>", lambda e: self.schedule_refresh())

        # Live Search
        Label(fb_content, text="Search:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#475569").pack(
            side=LEFT, padx=(0, 4)
        )
        self.search_entry = ttk.Entry(fb_content, textvariable=self.filter_vars["search"], width=22, font=("Segoe UI", 9))
        self.search_entry.pack(side=LEFT, padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", lambda e: self.schedule_refresh(delay_ms=250))

        # Reset Filter Button
        reset_btn = Button(
            fb_content,
            text="Reset Filters",
            command=self._reset_filters,
            bg="#f1f5f9",
            fg="#475569",
            font=("Segoe UI", 8, "bold"),
            relief=FLAT,
            cursor="hand2",
            padx=8,
            pady=3,
        )
        reset_btn.pack(side=LEFT, padx=4)

        # ---------------- 3. Notebook Multi-Tab Container ----------------
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=(0, 6))

        # Create Tab Frames
        self.tab_overview = self._create_scrollable_tab(self.notebook)
        self.tab_charts = self._create_scrollable_tab(self.notebook)
        self.tab_insights = self._create_scrollable_tab(self.notebook)
        self.tab_optimizer = self._create_scrollable_tab(self.notebook)
        self.tab_reports = self._create_scrollable_tab(self.notebook)

        self.notebook.add(self.tab_overview["container"], text="Overview & KPIs")
        self.notebook.add(self.tab_charts["container"], text="Visual Charts")
        self.notebook.add(self.tab_insights["container"], text="Forensic Insights")
        self.notebook.add(self.tab_optimizer["container"], text="Storage Optimizer")
        self.notebook.add(self.tab_reports["container"], text="Export & Reports")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed, add="+")

        # ---------------- 4. Bottom Status & Action Bar ----------------
        bottom_bar = Frame(self.window, bg="#1e293b", height=38)
        bottom_bar.pack(fill=X, side=BOTTOM)
        bottom_bar.pack_propagate(False)

        Label(
            bottom_bar,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#cbd5e1",
        ).pack(side=LEFT, padx=16, pady=8)

        close_btn = Button(
            bottom_bar,
            text="Close Dashboard",
            command=self.close,
            bg="#334155",
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief=FLAT,
            cursor="hand2",
            padx=16,
            pady=3,
        )
        close_btn.pack(side=RIGHT, padx=12, pady=4)

        # Global window mousewheel listeners as universal fallback
        self.window.bind("<MouseWheel>", lambda e: self._on_mousewheel(e), add="+")
        self.window.bind("<Shift-MouseWheel>", lambda e: self._on_shift_mousewheel(e), add="+")
        self.window.bind("<Button-4>", lambda e: self._on_mousewheel(e), add="+")
        self.window.bind("<Button-5>", lambda e: self._on_mousewheel(e), add="+")
        self.window.bind("<Shift-Button-4>", lambda e: self._on_shift_mousewheel(e), add="+")
        self.window.bind("<Shift-Button-5>", lambda e: self._on_shift_mousewheel(e), add="+")

        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def _create_scrollable_tab(self, notebook_parent) -> dict:
        """Create a responsive scrollable tab container with comprehensive mousewheel support."""
        container = Frame(notebook_parent, bg="#f5f7fa")
        canvas = Canvas(container, bg="#f5f7fa", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = Frame(canvas, bg="#f5f7fa")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def update_width(event=None):
            if canvas.winfo_exists():
                canvas.itemconfig(canvas_window, width=canvas.winfo_width())
                canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", update_width)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        # Bind mousewheel and hover listeners to container, canvas, scrollbar, and scrollable_frame
        self._bind_mousewheel_recursive(container, canvas)
        self._bind_mousewheel_recursive(canvas, canvas)
        self._bind_mousewheel_recursive(scrollbar, canvas)
        self._bind_mousewheel_recursive(scrollable_frame, canvas)

        return {
            "container": container,
            "frame": scrollable_frame,
            "canvas": canvas,
            "scrollbar": scrollbar,
        }

    def _on_mousewheel(self, event, target_canvas: Canvas | None = None) -> str | None:
        """Handle vertical mousewheel scrolling cross-platform for active or target canvas.

        Args:
            event: Tkinter event containing delta or num.
            target_canvas: Optional specific canvas to scroll; defaults to hovered or active canvas.

        Returns:
            str | None: 'break' to prevent duplicate bubbling.
        """
        canvas = target_canvas or self._hovered_canvas or self._get_active_canvas()
        if not canvas:
            return None

        try:
            if not canvas.winfo_exists():
                return None

            delta_steps = 0
            if sys.platform == "darwin":
                if hasattr(event, "delta") and event.delta != 0:
                    delta_steps = -1 * int(event.delta)
            elif hasattr(event, "delta") and event.delta:
                delta_steps = int(-1 * (event.delta / 120))
                if delta_steps == 0:
                    delta_steps = -1 if event.delta > 0 else 1
            elif getattr(event, "num", None) == 4:
                delta_steps = -1
            elif getattr(event, "num", None) == 5:
                delta_steps = 1

            if delta_steps:
                canvas.yview_scroll(delta_steps, "units")
                return "break"
        except Exception:
            pass
        return None

    def _on_shift_mousewheel(self, event, target_canvas: Canvas | None = None) -> str | None:
        """Handle horizontal mousewheel scrolling (Shift+Wheel) cross-platform.

        Args:
            event: Tkinter event containing delta or num.
            target_canvas: Optional specific canvas to scroll.

        Returns:
            str | None: 'break' to prevent duplicate bubbling.
        """
        canvas = target_canvas or self._hovered_canvas or self._get_active_canvas()
        if not canvas:
            return None

        try:
            if not canvas.winfo_exists():
                return None

            delta_steps = 0
            if sys.platform == "darwin":
                if hasattr(event, "delta") and event.delta != 0:
                    delta_steps = -1 * int(event.delta)
            elif hasattr(event, "delta") and event.delta:
                delta_steps = int(-1 * (event.delta / 120))
                if delta_steps == 0:
                    delta_steps = -1 if event.delta > 0 else 1
            elif getattr(event, "num", None) == 4:
                delta_steps = -1
            elif getattr(event, "num", None) == 5:
                delta_steps = 1

            if delta_steps:
                canvas.xview_scroll(delta_steps, "units")
                return "break"
        except Exception:
            pass
        return None

    def _get_active_canvas(self) -> Canvas | None:
        """Get the canvas widget belonging to the currently visible notebook tab.

        Returns:
            Canvas | None: Active tab's canvas or None if not found/available.
        """
        if not self.notebook or not self.window or not self.window.winfo_exists():
            return None
        try:
            current_tab = self.notebook.select()
            if not current_tab:
                return None
            for tab_data in [
                self.tab_overview,
                self.tab_charts,
                self.tab_insights,
                self.tab_optimizer,
                self.tab_reports,
            ]:
                if isinstance(tab_data, dict):
                    container = tab_data.get("container")
                    if container and str(container) == str(current_tab):
                        return tab_data.get("canvas")
        except Exception:
            pass
        return None

    def _on_tab_changed(self, event=None) -> None:
        """Reset hover focus when notebook tab changes to ensure scrolling follows active tab."""
        self._hovered_canvas = None

    def _bind_mousewheel_recursive(self, widget, canvas: Canvas) -> None:
        """Recursively bind mousewheel and hover listeners across widget hierarchies.

        Args:
            widget: Root widget to bind.
            canvas: Target Canvas associated with the widget hierarchy.
        """
        if not widget or not canvas:
            return

        def _handle_wheel(e):
            return self._on_mousewheel(e, target_canvas=canvas)

        def _handle_shift_wheel(e):
            return self._on_shift_mousewheel(e, target_canvas=canvas)

        def _set_hover(e):
            self._hovered_canvas = canvas

        def _clear_hover(e):
            if self._hovered_canvas is canvas:
                self._hovered_canvas = None

        def _bind_single(w):
            try:
                w.bind("<MouseWheel>", _handle_wheel, add="+")
                w.bind("<Shift-MouseWheel>", _handle_shift_wheel, add="+")
                w.bind("<Button-4>", _handle_wheel, add="+")
                w.bind("<Button-5>", _handle_wheel, add="+")
                w.bind("<Shift-Button-4>", _handle_shift_wheel, add="+")
                w.bind("<Shift-Button-5>", _handle_shift_wheel, add="+")
                w.bind("<Enter>", _set_hover, add="+")
                w.bind("<Leave>", _clear_hover, add="+")
            except Exception:
                pass

        _bind_single(widget)
        try:
            for child in widget.winfo_children():
                self._bind_mousewheel_recursive(child, canvas)
        except Exception:
            pass

    def _reset_filters(self) -> None:
        """Reset all filter controls to default states."""
        self.filter_vars["date_range"].set("All Time")
        self.filter_vars["file_type"].set("All Types")
        self.filter_vars["risk_level"].set("All Risks")
        self.filter_vars["search"].set("")
        self.schedule_refresh()

    def _cancel_pending_refresh(self) -> None:
        """Cancel pending debounce timers."""
        pending = self.dashboard_state.get("refresh_after_id")
        if pending is not None and self.window and self.window.winfo_exists():
            try:
                self.window.after_cancel(pending)
            except Exception:
                pass
            self.dashboard_state["refresh_after_id"] = None

    def schedule_refresh(self, delay_ms: int = 0, force_fetch: bool = False) -> None:
        """Schedule an asynchronous dashboard refresh."""
        self._cancel_pending_refresh()
        if not self.window or not self.window.winfo_exists():
            return

        if delay_ms > 0:
            self.dashboard_state["refresh_after_id"] = self.window.after(
                delay_ms, lambda: self.refresh_dashboard(force_fetch=force_fetch)
            )
        else:
            self.refresh_dashboard(force_fetch=force_fetch)

    def refresh_dashboard(self, force_fetch: bool = False) -> None:
        """Fetch records and calculate analytics asynchronously without freezing GUI."""
        self._cancel_pending_refresh()
        if not self.window or not self.window.winfo_exists():
            return

        self.dashboard_state["request_token"] += 1
        req_token = self.dashboard_state["request_token"]

        criteria = {
            "date_range": self.filter_vars["date_range"].get(),
            "file_type": self.filter_vars["file_type"].get(),
            "risk_level": self.filter_vars["risk_level"].get(),
            "search": self.filter_vars["search"].get(),
        }

        if self.refresh_btn:
            self.refresh_btn.config(state=DISABLED, text="Computing Analytics...")
        if self.status_var:
            self.status_var.set("Loading records and running forensic calculation...")

        start_time = time.time()

        def worker():
            try:
                use_cached = (
                    self.dashboard_state["records_cache"] is not None and not force_fetch
                )
                all_records = (
                    self.dashboard_state["records_cache"]
                    if use_cached
                    else (self.db.fetch_all_metadata() if self.db else [])
                )
                all_types = sorted(
                    {str(r[4]).upper() for r in all_records if len(r) > 4 and r[4]}
                )
                filtered = filter_records(all_records, criteria)
                stats = calculate_enhanced_stats(
                    filtered,
                    risk_analyzer_module=self.risk_analyzer,
                    risk_cache=self.dashboard_state["risk_cache"],
                )

                risk_sel = criteria.get("risk_level", "All Risks")
                if risk_sel and "All" not in risk_sel and stats:
                    target_risk = "HIGH" if "HIGH" in risk_sel else ("MEDIUM" if "MEDIUM" in risk_sel else "LOW")
                    filtered = [
                        r for r in filtered
                        if stats["record_risk_map"].get(r[0] if len(r) > 0 else 0) == target_risk
                    ]
                    stats = calculate_enhanced_stats(
                        filtered,
                        risk_analyzer_module=self.risk_analyzer,
                        risk_cache=self.dashboard_state["risk_cache"],
                    )

                calc_time = (time.time() - start_time) * 1000.0
                payload = (all_records, all_types, filtered, stats, calc_time, None)
            except Exception as err:
                payload = (None, None, None, None, 0, err)

            def apply_result():
                if not self.window or not self.window.winfo_exists():
                    return
                if req_token != self.dashboard_state["request_token"]:
                    return

                if self.refresh_btn:
                    self.refresh_btn.config(state=NORMAL, text="Refresh Analytics")

                all_records, all_types, filtered, stats, calc_time, error = payload
                if error is not None:
                    if self.status_var:
                        self.status_var.set(f"Error loading analytics: {error}")
                    return

                self.dashboard_state["records_cache"] = all_records
                self.dashboard_state["filtered_records"] = filtered
                self.dashboard_state["stats"] = stats

                if self.type_combo and all_types:
                    current_val = self.filter_vars["file_type"].get()
                    self.type_combo["values"] = ["All Types"] + all_types
                    if current_val not in (["All Types"] + all_types):
                        self.filter_vars["file_type"].set("All Types")

                total_all = len(all_records) if all_records else 0
                total_filtered = len(filtered) if filtered else 0
                if self.status_var:
                    self.status_var.set(
                        f"Showing {total_filtered} of {total_all} records • "
                        f"Total Volume: {format_size(stats['total_size'] if stats else 0)} • "
                        f"Calculation time: {calc_time:.1f}ms • Status: Ready"
                    )

                self._render_all_tabs(stats, filtered)

            if self.window and self.window.winfo_exists():
                self.window.after(0, apply_result)

        threading.Thread(target=worker, daemon=True).start()

    def _toggle_auto_refresh(self) -> None:
        """Toggle auto-refresh cycle every 30 seconds."""
        if self.filter_vars.get("auto_refresh") and self.filter_vars["auto_refresh"].get():
            def auto_update():
                if (
                    self.window
                    and self.window.winfo_exists()
                    and self.filter_vars["auto_refresh"].get()
                ):
                    self.schedule_refresh(force_fetch=True)
                    self.window.after(30000, auto_update)

            if self.window and self.window.winfo_exists():
                self.window.after(30000, auto_update)

    def _render_all_tabs(self, stats: dict | None, filtered_records: list) -> None:
        """Render all dashboard tabs with the latest aggregated analytics data."""
        self._render_tab_overview(stats, filtered_records)
        self._render_tab_charts(stats, filtered_records)
        self._render_tab_insights(stats, filtered_records)
        self._render_tab_optimizer(stats, filtered_records)
        self._render_tab_reports(stats, filtered_records)

    # ------------------------------------------------------------------
    # TAB 1: Overview & KPI Summary
    # ------------------------------------------------------------------
    def _render_tab_overview(self, stats: dict | None, filtered_records: list) -> None:
        frame = self.tab_overview["frame"]
        canvas = self.tab_overview.get("canvas")
        for child in frame.winfo_children():
            child.destroy()

        if stats is None or stats["total"] == 0:
            self._render_empty_state(frame, "No Matching Records Found", canvas=canvas)
            return

        summary_card = Frame(frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        summary_card.pack(fill=X, padx=14, pady=(12, 10))

        summary_inner = Frame(summary_card, bg="#ffffff")
        summary_inner.pack(fill=BOTH, expand=True, padx=16, pady=12)

        Label(
            summary_inner,
            text="Executive Intelligence Summary",
            font=("Segoe UI", 11, "bold"),
            bg="#ffffff",
            fg="#1e293b",
            anchor=W,
        ).pack(fill=X, pady=(0, 4))

        Label(
            summary_inner,
            text=stats.get("executive_summary", ""),
            font=("Segoe UI", 10),
            bg="#ffffff",
            fg="#475569",
            wraplength=950,
            justify=LEFT,
            anchor=W,
        ).pack(fill=X)

        kpi_row1 = Frame(frame, bg="#f5f7fa")
        kpi_row1.pack(fill=X, padx=10, pady=(0, 6))

        create_metric_card(
            kpi_row1,
            "Total Files",
            str(stats["total"]),
            "Analyzed Records",
            "#667eea",
            "#5a67d8",
            badge="ACTIVE",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=4)

        create_metric_card(
            kpi_row1,
            "Storage Volume",
            format_size(stats["total_size"]),
            f"Avg {format_size(stats['avg_size'])}/file",
            "#4facfe",
            "#00f2fe",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=4)

        create_metric_card(
            kpi_row1,
            "File Formats",
            str(len(stats["file_types"])),
            f"Top: {max(stats['file_types'], key=stats['file_types'].get).upper() if stats['file_types'] else 'N/A'}",
            "#43e97b",
            "#38f9d7",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=4)

        create_metric_card(
            kpi_row1,
            "Metadata Score",
            f"{stats.get('avg_completeness', 0):.1f}%",
            "Completeness Audit",
            "#fa709a",
            "#fee140",
            badge="AUDIT",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=4)

        kpi_row2 = Frame(frame, bg="#f5f7fa")
        kpi_row2.pack(fill=X, padx=10, pady=(0, 10))

        high_risk_n = stats["risk_counts"].get("HIGH", 0)
        create_metric_card(
            kpi_row2,
            "High Risk Privacy",
            str(high_risk_n),
            "Requires immediate review",
            "#e74c3c",
            "#c0392b",
            badge="CRITICAL" if high_risk_n > 0 else "CLEAR",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=4)

        create_metric_card(
            kpi_row2,
            "Moderate Risk",
            str(stats["risk_counts"].get("MEDIUM", 0)),
            "Potential metadata leaks",
            "#f39c12",
            "#d35400",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=4)

        create_metric_card(
            kpi_row2,
            "Low Risk Safe",
            str(stats["risk_counts"].get("LOW", 0)),
            "Clean / Sanitized files",
            "#27ae60",
            "#2ecc71",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=4)

        create_metric_card(
            kpi_row2,
            "Duplicate Files",
            str(len(stats.get("duplicates", []))),
            "Redundant copies identified",
            "#8e44ad",
            "#9b59b6",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=4)

        recent_card = Frame(frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        recent_card.pack(fill=X, padx=14, pady=(4, 16))

        recent_header = Frame(recent_card, bg="#ffffff")
        recent_header.pack(fill=X, padx=16, pady=(12, 6))

        Label(
            recent_header,
            text="Recent Ingestion Activity",
            font=("Segoe UI", 11, "bold"),
            bg="#ffffff",
            fg="#1e293b",
        ).pack(side=LEFT)

        Label(
            recent_header,
            text="Latest analyzed items",
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#94a3b8",
        ).pack(side=LEFT, padx=8)

        recent_items = sorted(
            filtered_records,
            key=lambda x: x[5] if len(x) > 5 and x[5] else "",
            reverse=True,
        )[:5]

        for i, rec in enumerate(recent_items, 1):
            row_box = Frame(recent_card, bg="#ffffff", highlightbackground="#f1f5f9", highlightthickness=1)
            row_box.pack(fill=X, padx=16, pady=4)

            idx_lbl = Label(
                row_box,
                text=str(i),
                font=("Segoe UI", 9, "bold"),
                bg="#667eea",
                fg="#ffffff",
                width=3,
            )
            idx_lbl.pack(side=LEFT, padx=(8, 12), pady=6)

            info_box = Frame(row_box, bg="#ffffff")
            info_box.pack(side=LEFT, fill=X, expand=True, pady=4)

            Label(
                info_box,
                text=rec[2] if len(rec) > 2 else "Unknown",
                font=("Segoe UI", 9, "bold"),
                bg="#ffffff",
                fg="#1e293b",
                anchor=W,
            ).pack(fill=X)

            Label(
                info_box,
                text=f"Path: {rec[1][:70] if len(rec) > 1 else ''} • Format: {rec[4] if len(rec) > 4 else ''} • Size: {rec[3] if len(rec) > 3 else ''} • Extracted: {rec[5] if len(rec) > 5 else ''}",
                font=("Segoe UI", 8),
                bg="#ffffff",
                fg="#64748b",
                anchor=W,
            ).pack(fill=X)

        if canvas:
            self._bind_mousewheel_recursive(frame, canvas)
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # TAB 2: Visual Charts & Analytics
    # ------------------------------------------------------------------
    def _render_tab_charts(self, stats: dict | None, filtered_records: list) -> None:
        frame = self.tab_charts["frame"] if isinstance(self.tab_charts, dict) else self.tab_charts
        canvas = self.tab_charts.get("canvas") if isinstance(self.tab_charts, dict) else None
        for child in frame.winfo_children():
            child.destroy()

        if stats is None or stats["total"] == 0:
            self._render_empty_state(frame, "No Data for Visual Charts", canvas=canvas)
            return

        chart_top_bar = Frame(frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        chart_top_bar.pack(fill=X, padx=14, pady=(10, 6))

        Label(
            chart_top_bar,
            text="Interactive Visual Analytics Suite",
            font=("Segoe UI", 11, "bold"),
            bg="#ffffff",
            fg="#1e293b",
        ).pack(side=LEFT, padx=14, pady=8)

        export_chart_btn = Button(
            chart_top_bar,
            text="Export Charts Image (PNG)",
            command=self._export_chart_image,
            bg="#f1f5f9",
            fg="#334155",
            font=("Segoe UI", 9, "bold"),
            relief=FLAT,
            cursor="hand2",
            padx=10,
            pady=4,
        )
        export_chart_btn.pack(side=RIGHT, padx=14, pady=6)

        fig_container = Frame(frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        fig_container.pack(fill=BOTH, expand=True, padx=14, pady=(0, 10))

        fig = Figure(figsize=(11, 6), facecolor="#ffffff", dpi=100)
        self.active_figure = fig

        # Subplot 1: File Type Donut Chart
        ax1 = fig.add_subplot(221)
        if stats["file_types"]:
            types = list(stats["file_types"].keys())
            counts = list(stats["file_types"].values())
            colors = self.CHART_PALETTES["modern"][: len(types)]
            wedges, texts, autotexts = ax1.pie(
                counts,
                labels=[t.upper() for t in types],
                autopct="%1.0f%%",
                colors=colors,
                startangle=140,
                wedgeprops=dict(width=0.45, edgecolor="white", linewidth=2),
                textprops=dict(fontsize=8, color="#334155"),
            )
            for at in autotexts:
                at.set_fontsize(7)
                at.set_color("#1e293b")
            ax1.set_title("File Format Distribution", fontsize=10, weight="bold", pad=8, color="#1e293b")

        # Subplot 2: Storage by Format (Horizontal Bar)
        ax2 = fig.add_subplot(222)
        if stats.get("total_size_by_type"):
            sorted_storage = sorted(stats["total_size_by_type"].items(), key=lambda x: x[1], reverse=True)[:6]
            labels = [s[0].upper() for s in sorted_storage]
            sizes_mb = [s[1] / (1024 * 1024) for s in sorted_storage]
            y_pos = range(len(labels))
            ax2.barh(y_pos, sizes_mb, color="#4facfe", edgecolor="white", height=0.6)
            ax2.set_yticks(y_pos)
            ax2.set_yticklabels(labels, fontsize=8, color="#334155")
            ax2.set_xlabel("Volume (MB)", fontsize=8, color="#64748b")
            ax2.set_title("Storage Volume by Format", fontsize=10, weight="bold", pad=8, color="#1e293b")
            ax2.invert_yaxis()
            ax2.grid(axis="x", linestyle="--", alpha=0.3)

        # Subplot 3: Timeline Ingestion Trends
        ax3 = fig.add_subplot(223)
        if stats["files_by_date"]:
            sorted_dates = sorted(stats["files_by_date"].items())
            dates = [datetime.strptime(d, "%Y-%m-%d") for d, _ in sorted_dates]
            counts = [c for _, c in sorted_dates]
            ax3.plot(dates, counts, color="#667eea", linewidth=2, marker="o", markersize=4)
            ax3.fill_between(dates, counts, alpha=0.25, color="#667eea")
            ax3.set_ylabel("Records", fontsize=8, color="#64748b")
            ax3.set_title("Temporal Extraction Trends", fontsize=10, weight="bold", pad=8, color="#1e293b")
            ax3.grid(axis="y", linestyle="--", alpha=0.3)
            plt.setp(ax3.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=7)

        # Subplot 4: Privacy Risk Distribution Bar
        ax4 = fig.add_subplot(224)
        risk_labels = ["LOW", "MEDIUM", "HIGH"]
        risk_vals = [stats["risk_counts"].get(r, 0) for r in risk_labels]
        risk_colors = ["#27ae60", "#f39c12", "#e74c3c"]
        bars = ax4.bar(risk_labels, risk_vals, color=risk_colors, width=0.5, edgecolor="white")
        ax4.set_ylabel("Files", fontsize=8, color="#64748b")
        ax4.set_title("Privacy Risk Distribution", fontsize=10, weight="bold", pad=8, color="#1e293b")
        ax4.grid(axis="y", linestyle="--", alpha=0.3)
        for bar in bars:
            h = bar.get_height()
            ax4.annotate(
                f"{h}",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 2),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
                weight="bold",
            )

        fig.tight_layout(pad=2.0)
        self.chart_canvas = FigureCanvasTkAgg(fig, master=fig_container)
        self.chart_canvas.draw()
        self.chart_canvas.get_tk_widget().pack(fill=BOTH, expand=True, padx=8, pady=8)

        if canvas:
            self._bind_mousewheel_recursive(frame, canvas)
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

    def _export_chart_image(self) -> None:
        """Export active matplotlib chart figure to PNG file."""
        if not self.active_figure:
            messagebox.showwarning("No Chart", "No active chart to export.")
            return
        filepath = filedialog.asksaveasfilename(
            title="Export Charts as Image",
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")],
        )
        if filepath:
            try:
                self.active_figure.savefig(filepath, dpi=200, bbox_inches="tight")
                messagebox.showinfo("Export Successful", f"Chart saved to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Failed to save chart: {e}")

    # ------------------------------------------------------------------
    # TAB 3: Forensic & Metadata Insights
    # ------------------------------------------------------------------
    def _render_tab_insights(self, stats: dict | None, filtered_records: list) -> None:
        frame = self.tab_insights["frame"]
        canvas = self.tab_insights.get("canvas")
        for child in frame.winfo_children():
            child.destroy()

        if stats is None or stats["total"] == 0:
            self._render_empty_state(frame, "No Forensic Data Available", canvas=canvas)
            return

        card1 = Frame(frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        card1.pack(fill=X, padx=14, pady=(12, 8))

        c1_head = Frame(card1, bg="#ffffff")
        c1_head.pack(fill=X, padx=16, pady=(12, 6))
        Label(c1_head, text="Forensic Anomaly & Duplicate Detection", font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#1e293b").pack(side=LEFT)

        dups = stats.get("duplicates", [])
        if dups:
            dup_txt = f"Identified {len(dups)} duplicate file name group{'s' if len(dups) != 1 else ''} across the database:"
            Label(card1, text=dup_txt, font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#e74c3c", anchor=W).pack(fill=X, padx=16, pady=(0, 6))

            for d in dups[:6]:
                d_row = Frame(card1, bg="#fef2f2", highlightbackground="#fecaca", highlightthickness=1)
                d_row.pack(fill=X, padx=16, pady=3)
                Label(d_row, text=f"• {d['filename']}", font=("Segoe UI", 9, "bold"), bg="#fef2f2", fg="#991b1b").pack(side=LEFT, padx=8, pady=4)
                Label(d_row, text=f"{d['count']} duplicate instances", font=("Segoe UI", 8), bg="#fef2f2", fg="#b91c1c").pack(side=RIGHT, padx=8)
        else:
            Label(card1, text="Zero duplicate file names detected. Database records are clean.", font=("Segoe UI", 9), bg="#ffffff", fg="#27ae60", anchor=W).pack(fill=X, padx=16, pady=(0, 12))

        card2 = Frame(frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        card2.pack(fill=X, padx=14, pady=6)

        c2_head = Frame(card2, bg="#ffffff")
        c2_head.pack(fill=X, padx=16, pady=(12, 6))
        Label(c2_head, text="Metadata Completeness Audit", font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#1e293b").pack(side=LEFT)

        grid_frame = Frame(card2, bg="#ffffff")
        grid_frame.pack(fill=X, padx=16, pady=(0, 12))

        top_keys = stats.get("metadata_keys", Counter()).most_common(8)
        for i, (k, cnt) in enumerate(top_keys):
            row_idx = i // 2
            col_idx = i % 2
            pct = (cnt / stats["total"]) * 100.0
            lbl_box = Frame(grid_frame, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
            lbl_box.grid(row=row_idx, column=col_idx, sticky="ew", padx=6, pady=4)
            grid_frame.columnconfigure(col_idx, weight=1)

            Label(lbl_box, text=k, font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#334155").pack(side=LEFT, padx=8, pady=4)
            Label(lbl_box, text=f"{pct:.0f}% ({cnt} files)", font=("Segoe UI", 8), bg="#f8fafc", fg="#64748b").pack(side=RIGHT, padx=8)

        card3 = Frame(frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        card3.pack(fill=X, padx=14, pady=(6, 16))

        c3_head = Frame(card3, bg="#ffffff")
        c3_head.pack(fill=X, padx=16, pady=(12, 6))
        Label(c3_head, text="Author & Creation Software Intelligence", font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#1e293b").pack(side=LEFT)

        authors = stats.get("authors", Counter()).most_common(5)
        software = stats.get("software", Counter()).most_common(5)

        sub_grid = Frame(card3, bg="#ffffff")
        sub_grid.pack(fill=X, padx=16, pady=(0, 12))
        sub_grid.columnconfigure(0, weight=1)
        sub_grid.columnconfigure(1, weight=1)

        auth_box = Frame(sub_grid, bg="#ffffff")
        auth_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        Label(auth_box, text="Top Identified Authors / Creators:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#475569", anchor=W).pack(fill=X, pady=(0, 4))
        if authors:
            for a, c in authors:
                Label(auth_box, text=f"• {a} ({c} files)", font=("Segoe UI", 8), bg="#ffffff", fg="#1e293b", anchor=W).pack(fill=X)
        else:
            Label(auth_box, text="No author metadata recorded.", font=("Segoe UI", 8), bg="#ffffff", fg="#94a3b8", anchor=W).pack(fill=X)

        soft_box = Frame(sub_grid, bg="#ffffff")
        soft_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        Label(soft_box, text="Top Creation Applications:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#475569", anchor=W).pack(fill=X, pady=(0, 4))
        if software:
            for s, c in software:
                Label(soft_box, text=f"• {s} ({c} files)", font=("Segoe UI", 8), bg="#ffffff", fg="#1e293b", anchor=W).pack(fill=X)
        else:
            Label(soft_box, text="No software metadata recorded.", font=("Segoe UI", 8), bg="#ffffff", fg="#94a3b8", anchor=W).pack(fill=X)

        if canvas:
            self._bind_mousewheel_recursive(frame, canvas)
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # TAB 4: Storage Optimization & Recommendations
    # ------------------------------------------------------------------
    def _render_tab_optimizer(self, stats: dict | None, filtered_records: list) -> None:
        frame = self.tab_optimizer["frame"]
        canvas = self.tab_optimizer.get("canvas")
        for child in frame.winfo_children():
            child.destroy()

        if stats is None or stats["total"] == 0:
            self._render_empty_state(frame, "No Storage Optimization Data Available", canvas=canvas)
            return

        rec_card = Frame(frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        rec_card.pack(fill=X, padx=14, pady=(12, 8))

        rc_head = Frame(rec_card, bg="#ffffff")
        rc_head.pack(fill=X, padx=16, pady=(12, 6))
        Label(rc_head, text="Smart Storage Optimization Insights", font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#1e293b").pack(side=LEFT)

        total_mb = stats["total_size"] / (1024 * 1024)
        top5_size = sum(s[0] for s in stats.get("largest_files", [])[:5])
        top5_pct = (top5_size / stats["total_size"] * 100.0) if stats["total_size"] > 0 else 0

        insights_list = [
            f"• Top 5 largest files account for {format_size(top5_size)} ({top5_pct:.1f}% of entire volume).",
            f"• Average file footprint is {format_size(stats['avg_size'])}.",
            f"• Found {len(stats.get('duplicates', []))} potential duplicate file names for cleanup.",
            f"• {stats['risk_counts'].get('HIGH', 0)} files flagged with high privacy exposure requiring sanitization.",
        ]

        for ins in insights_list:
            Label(rec_card, text=ins, font=("Segoe UI", 9), bg="#ffffff", fg="#475569", anchor=W).pack(fill=X, padx=16, pady=2)
        Label(rec_card, text="", bg="#ffffff").pack(pady=4)

        top_card = Frame(frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        top_card.pack(fill=X, padx=14, pady=(6, 16))

        tc_head = Frame(top_card, bg="#ffffff")
        tc_head.pack(fill=X, padx=16, pady=(12, 6))
        Label(tc_head, text="Top 10 Storage Consumers", font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#1e293b").pack(side=LEFT)

        for i, (size_bytes, fname) in enumerate(stats.get("largest_files", []), 1):
            row = Frame(top_card, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
            row.pack(fill=X, padx=16, pady=3)

            badge = Label(row, text=str(i), font=("Segoe UI", 9, "bold"), bg="#4facfe", fg="#ffffff", width=3)
            badge.pack(side=LEFT, padx=(6, 10), pady=4)

            Label(row, text=fname, font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#1e293b", anchor=W).pack(side=LEFT, fill=X, expand=True)

            size_pct = (size_bytes / stats["total_size"] * 100.0) if stats["total_size"] > 0 else 0
            Label(row, text=f"{format_size(size_bytes)}  ({size_pct:.1f}%)", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#475569").pack(side=RIGHT, padx=10)

        if canvas:
            self._bind_mousewheel_recursive(frame, canvas)
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # TAB 5: Export & Reporting Center
    # ------------------------------------------------------------------
    def _render_tab_reports(self, stats: dict | None, filtered_records: list) -> None:
        frame = self.tab_reports["frame"]
        canvas = self.tab_reports.get("canvas")
        for child in frame.winfo_children():
            child.destroy()

        if stats is None or stats["total"] == 0:
            self._render_empty_state(frame, "No Data for Export", canvas=canvas)
            return

        export_card = Frame(frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        export_card.pack(fill=X, padx=14, pady=(12, 10))

        ec_head = Frame(export_card, bg="#ffffff")
        ec_head.pack(fill=X, padx=16, pady=(12, 6))
        Label(ec_head, text="Forensic Export & Reporting Center", font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#1e293b").pack(side=LEFT)

        Label(
            export_card,
            text="Generate structured analytical reports across multiple formats for audits, compliance, and archiving.",
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#64748b",
            anchor=W,
        ).pack(fill=X, padx=16, pady=(0, 12))

        btn_grid = Frame(export_card, bg="#ffffff")
        btn_grid.pack(fill=X, padx=16, pady=(0, 16))

        Button(
            btn_grid,
            text="Export Full Records (CSV)",
            command=lambda: self._export_csv(filtered_records),
            bg="#27ae60",
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief=FLAT,
            cursor="hand2",
            padx=14,
            pady=8,
        ).pack(side=LEFT, padx=(0, 10))

        Button(
            btn_grid,
            text="Export Analytics (JSON)",
            command=lambda: self._export_json(stats, filtered_records),
            bg="#667eea",
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief=FLAT,
            cursor="hand2",
            padx=14,
            pady=8,
        ).pack(side=LEFT, padx=(0, 10))

        Button(
            btn_grid,
            text="Copy Summary to Clipboard",
            command=lambda: self._copy_summary(stats),
            bg="#f1f5f9",
            fg="#1e293b",
            font=("Segoe UI", 9, "bold"),
            relief=FLAT,
            cursor="hand2",
            padx=14,
            pady=8,
        ).pack(side=LEFT)

        if canvas:
            self._bind_mousewheel_recursive(frame, canvas)
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

    def _export_csv(self, filtered_records: list) -> None:
        """Export analyzed records to a CSV file."""
        filepath = filedialog.asksaveasfilename(
            title="Export Records to CSV",
            defaultextension=".csv",
            filetypes=[("CSV File", "*.csv"), ("All Files", "*.*")],
        )
        if filepath:
            try:
                with open(filepath, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["ID", "File Path", "File Name", "Size", "Type", "Extracted At", "Modified On"])
                    for r in filtered_records:
                        writer.writerow([r[i] if len(r) > i else "" for i in range(7)])
                messagebox.showinfo("Export Successful", f"Saved {len(filtered_records)} records to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export CSV: {e}")

    def _export_json(self, stats: dict, filtered_records: list) -> None:
        """Export statistical summary and records to JSON file."""
        filepath = filedialog.asksaveasfilename(
            title="Export Analytics to JSON",
            defaultextension=".json",
            filetypes=[("JSON File", "*.json"), ("All Files", "*.*")],
        )
        if filepath:
            try:
                payload = {
                    "generated_at": datetime.now().isoformat(),
                    "total_records": stats["total"],
                    "total_storage_bytes": stats["total_size"],
                    "file_types": stats["file_types"],
                    "risk_distribution": stats["risk_counts"],
                    "completeness_score": stats.get("avg_completeness", 0),
                    "executive_summary": stats.get("executive_summary", ""),
                }
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=4)
                messagebox.showinfo("Export Successful", f"Saved JSON report to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export JSON: {e}")

    def _copy_summary(self, stats: dict) -> None:
        """Copy the executive narrative to clipboard."""
        summary = stats.get("executive_summary", "")
        if summary and self.window:
            self.window.clipboard_clear()
            self.window.clipboard_append(summary)
            messagebox.showinfo("Copied", "Executive Intelligence Summary copied to clipboard!")

    def _render_empty_state(self, parent_frame: Frame, title: str, canvas: Canvas | None = None) -> None:
        """Render a clean empty state card when no matching data is found."""
        empty_box = Frame(parent_frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        empty_box.pack(fill=BOTH, expand=True, padx=20, pady=40)

        Label(
            empty_box,
            text=title,
            font=("Segoe UI", 14, "bold"),
            bg="#ffffff",
            fg="#64748b",
        ).pack(pady=(40, 6))

        Label(
            empty_box,
            text="Try adjusting search queries, changing period filters, or ingesting new files in TraceLens.",
            font=("Segoe UI", 10),
            bg="#ffffff",
            fg="#94a3b8",
        ).pack(pady=(0, 40))

        if canvas:
            self._bind_mousewheel_recursive(empty_box, canvas)

    def close(self) -> None:
        """Safely destroy dashboard window and release resources."""
        self._cancel_pending_refresh()
        self._hovered_canvas = None
        if self.window and self.window.winfo_exists():
            try:
                self.window.unbind("<MouseWheel>")
                self.window.unbind("<Shift-MouseWheel>")
                self.window.unbind("<Button-4>")
                self.window.unbind("<Button-5>")
                self.window.unbind("<Shift-Button-4>")
                self.window.unbind("<Shift-Button-5>")
            except Exception:
                pass
            self.window.destroy()
            self.window = None


def open_statistics_dashboard(parent=None) -> StatisticsDashboard:
    """Convenience function to open and show the Statistics Dashboard.

    Args:
        parent: Optional parent Tkinter widget.

    Returns:
        StatisticsDashboard: The instantiated dashboard controller.
    """
    dashboard = StatisticsDashboard(parent=parent)
    dashboard.show()
    return dashboard
