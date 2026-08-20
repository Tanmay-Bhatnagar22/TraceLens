"""Statistical Dashboard module for TraceLens application.

Provides interactive analytics, material design metrics, visual charts,
and metadata insights for extracted file records.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import (
    BOTH,
    BOTTOM,
    DISABLED,
    FLAT,
    LEFT,
    NORMAL,
    RIGHT,
    SOLID,
    TOP,
    X,
    Y,
    W,
    BooleanVar,
    Button,
    Canvas,
    Frame,
    Label,
    StringVar,
    Toplevel,
    ttk,
)

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
                'B': 1,
                'KB': 1024,
                'MB': 1024**2,
                'GB': 1024**3,
                'TB': 1024**4,
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

    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if val < 1024.0 or unit == 'TB':
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} TB"


def filter_records(records: list, criteria: dict) -> list:
    """Apply date range, file type, and search filters to database records.
    
    Args:
        records: List of database rows/tuples.
        criteria: Dict containing 'date_range', 'file_type', and 'search'.
        
    Returns:
        list: Filtered records.
    """
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
    search_term = criteria.get('search', '').lower().strip()
    if search_term:
        filtered = [
            r for r in filtered
            if len(r) > 2 and search_term in str(r[2]).lower()
        ]

    return filtered


def calculate_enhanced_stats(
    records: list,
    risk_analyzer_module=None,
    risk_cache: dict | None = None
) -> dict | None:
    """Calculate aggregated metrics and distribution statistics from records.
    
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

    stats = {
        'total': total,
        'file_types': {},
        'total_size': 0,
        'file_sizes': [],
        'sizes_by_type': defaultdict(list),
        'dates': [],
        'files_by_date': defaultdict(int),
        'risk_counts': {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0},
    }

    for record in records:
        ft = record[4] if len(record) > 4 and record[4] else "Unknown"
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

        if risk_analyzer_module and len(record) > 7 and record[7]:
            try:
                cache_key = (
                    record[0] if len(record) > 0 else None,
                    record[5] if len(record) > 5 else None,
                    record[6] if len(record) > 6 else None,
                )
                risk_level = risk_cache.get(cache_key)
                if risk_level is None:
                    parsed_metadata = (
                        json.loads(record[7])
                        if isinstance(record[7], str)
                        else (record[7] or {})
                    )
                    record_path = record[1] if len(record) > 1 else ""
                    fallback_ctime = None
                    if record_path and os.path.exists(record_path):
                        try:
                            fallback_ctime = datetime.fromtimestamp(
                                os.path.getctime(record_path)
                            ).isoformat(sep=" ", timespec="seconds")
                        except Exception:
                            pass

                    risk_result = risk_analyzer_module.analyze_metadata(
                        parsed_metadata,
                        record_path,
                        fallback_timestamps={
                            "Created Date": fallback_ctime,
                            "Modified Date": record[6] if len(record) > 6 else None,
                            "Extraction Date": record[5] if len(record) > 5 else None,
                        },
                    )
                    risk_level = risk_result.get('risk_level', 'LOW')
                    risk_cache[cache_key] = risk_level
                stats['risk_counts'][risk_level] = stats['risk_counts'].get(risk_level, 0) + 1
            except Exception:
                pass

    stats['avg_size'] = stats['total_size'] / total if total > 0 else 0
    stats['max_size'] = (
        max(stats['file_sizes'], key=lambda x: x[0])
        if stats['file_sizes']
        else (0, "Unknown")
    )
    non_zero_sizes = [f for f in stats['file_sizes'] if f[0] > 0]
    stats['min_size'] = (
        min(non_zero_sizes, key=lambda x: x[0])
        if non_zero_sizes
        else (0, "Unknown")
    )
    stats['largest_files'] = sorted(
        stats['file_sizes'], key=lambda x: x[0], reverse=True
    )[:10]
    stats['avg_size_by_type'] = {
        ft: sum(sizes) / len(sizes) if sizes else 0
        for ft, sizes in stats['sizes_by_type'].items()
    }

    return stats


def create_metric_card(
    parent,
    title: str,
    value: str,
    subtitle: str = "",
    bg_start: str = "#667eea",
    bg_end: str = "#764ba2",
    width: int | None = None,
) -> Frame:
    """Create a material design-style card with gradient simulation and hover effects.
    
    Args:
        parent: Parent widget.
        title: Card title/metric name.
        value: Main value to display.
        subtitle: Optional subtitle text.
        bg_start: Gradient start / primary background color.
        bg_end: Hover state background color.
        width: Optional fixed width.
        
    Returns:
        Frame: The created card container frame.
    """
    card_container = Frame(parent, bg="#e8e8e8", highlightthickness=0)

    card = Frame(card_container, bg=bg_start, highlightthickness=0)
    card.pack(padx=3, pady=3, fill=BOTH, expand=True)

    content_frame = Frame(card, bg=bg_start)
    content_frame.pack(fill=BOTH, expand=True, padx=20, pady=18)

    title_label = Label(
        content_frame,
        text=title,
        font=("Segoe UI", 10, "bold"),
        bg=bg_start,
        fg="white",
        anchor=W,
    )
    title_label.pack(fill=X, pady=(0, 8))

    value_label = Label(
        content_frame,
        text=value,
        font=("Segoe UI", 24, "bold"),
        bg=bg_start,
        fg="white",
        anchor=W,
    )
    value_label.pack(fill=X, pady=(0, 5))

    subtitle_label = None
    if subtitle:
        subtitle_label = Label(
            content_frame,
            text=subtitle,
            font=("Segoe UI", 9),
            bg=bg_start,
            fg="#f0f0f0",
            anchor=W,
        )
        subtitle_label.pack(fill=X)

    def on_enter(e):
        card.config(bg=bg_end)
        content_frame.config(bg=bg_end)
        title_label.config(bg=bg_end)
        value_label.config(bg=bg_end)
        if subtitle_label:
            subtitle_label.config(bg=bg_end)

    def on_leave(e):
        card.config(bg=bg_start)
        content_frame.config(bg=bg_start)
        title_label.config(bg=bg_start)
        value_label.config(bg=bg_start)
        if subtitle_label:
            subtitle_label.config(bg=bg_start)

    for widget in (card_container, card, content_frame, title_label, value_label):
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
    if subtitle_label:
        subtitle_label.bind("<Enter>", on_enter)
        subtitle_label.bind("<Leave>", on_leave)

    return card_container


class StatisticsDashboard:
    """Statistical Dashboard window displaying analytics, charts, and metrics."""

    GRADIENT_COLORS = [
        '#667eea',
        '#764ba2',
        '#f093fb',
        '#4facfe',
        '#43e97b',
        '#fa709a',
        '#fee140',
        '#30cfd0',
    ]

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
        self.scrollable_frame: Frame | None = None
        self.refresh_btn: Button | None = None
        self.type_combo: ttk.Combobox | None = None
        self.window_w = 800
        self.window_h = 600

        self.filter_vars = {}
        self.dashboard_state = {
            'refresh_after_id': None,
            'request_token': 0,
            'records_cache': None,
            'risk_cache': {},
        }

    def show(self) -> Toplevel:
        """Create and display the Statistics Dashboard modal dialog."""
        self.window = Toplevel(self.parent) if self.parent else Toplevel()
        self.window.title("Statistics Dashboard")
        self.window.config(bg="#f0f2f5")

        # Responsive window sizing (0.75 of screen size)
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        self.window_w = int(screen_width * 0.75)
        self.window_h = int(screen_height * 0.75)
        x = (screen_width - self.window_w) // 2
        y = (screen_height - self.window_h) // 2
        self.window.geometry(f"{self.window_w}x{self.window_h}+{x}+{y}")
        self.window.minsize(800, 600)

        if self.parent:
            self.window.transient(self.parent)
            self.window.grab_set()

        self.filter_vars = {
            'date_range': StringVar(value="All Time"),
            'file_type': StringVar(value="All Types"),
            'search': StringVar(value=""),
            'auto_refresh': BooleanVar(value=False),
        }

        self._build_ui()
        self.schedule_refresh(force_fetch=True)
        return self.window

    def _build_ui(self) -> None:
        """Construct dashboard header, filter bar, scroll area, and footer."""
        # Modern header
        header_frame = Frame(self.window, bg="#667eea", height=90)
        header_frame.pack(fill=X)
        header_frame.pack_propagate(False)

        header_content = Frame(header_frame, bg="#667eea")
        header_content.pack(fill=BOTH, expand=True, padx=20, pady=10)

        Label(
            header_content,
            text="Statistical Dashboard",
            font=("Segoe UI", 20, "bold"),
            bg="#667eea",
            fg="white",
        ).pack(side=LEFT)

        self.refresh_btn = Button(
            header_content,
            text="⟳ Refresh",
            command=lambda: self.schedule_refresh(force_fetch=True),
            bg="#5a67d8",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief=FLAT,
            cursor="hand2",
            padx=15,
            pady=8,
        )
        self.refresh_btn.pack(side=RIGHT, padx=5)

        auto_check = ttk.Checkbutton(
            header_content,
            text="Auto-refresh",
            variable=self.filter_vars['auto_refresh'],
            command=self._toggle_auto_refresh,
        )
        auto_check.pack(side=RIGHT, padx=10)

        # Filter bar
        filter_frame = Frame(self.window, bg="white", height=60)
        filter_frame.pack(fill=X, padx=10, pady=(10, 0))
        filter_frame.pack_propagate(False)

        filter_content = Frame(filter_frame, bg="white")
        filter_content.pack(fill=BOTH, expand=True, padx=10, pady=10)

        Label(
            filter_content,
            text="Period:",
            font=("Segoe UI", 10, "bold"),
            bg="white",
        ).pack(side=LEFT, padx=(0, 5))

        date_combo = ttk.Combobox(
            filter_content,
            textvariable=self.filter_vars['date_range'],
            values=[
                "All Time",
                "Last 7 Days",
                "Last 30 Days",
                "Last 90 Days",
                "This Year",
            ],
            state="readonly",
            width=15,
        )
        date_combo.pack(side=LEFT, padx=5)
        date_combo.bind('<<ComboboxSelected>>', lambda e: self.schedule_refresh())

        Label(
            filter_content,
            text="Type:",
            font=("Segoe UI", 10, "bold"),
            bg="white",
        ).pack(side=LEFT, padx=(20, 5))

        self.type_combo = ttk.Combobox(
            filter_content,
            textvariable=self.filter_vars['file_type'],
            state="readonly",
            width=15,
        )
        self.type_combo.pack(side=LEFT, padx=5)
        self.type_combo.bind('<<ComboboxSelected>>', lambda e: self.schedule_refresh())

        Label(
            filter_content,
            text="Search:",
            font=("Segoe UI", 10, "bold"),
            bg="white",
        ).pack(side=LEFT, padx=(20, 5))

        search_entry = ttk.Entry(
            filter_content, textvariable=self.filter_vars['search'], width=25
        )
        search_entry.pack(side=LEFT, padx=5)
        search_entry.bind(
            '<KeyRelease>', lambda e: self.schedule_refresh(delay_ms=350)
        )

        apply_btn = Button(
            filter_content,
            text="Apply Filters",
            command=lambda: self.schedule_refresh(),
            bg="#667eea",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief=FLAT,
            cursor="hand2",
            padx=12,
            pady=5,
        )
        apply_btn.pack(side=RIGHT, padx=5)

        # Scrollable container
        container = Frame(self.window, bg="#f0f2f5")
        container.pack(fill=BOTH, expand=True, padx=0, pady=0)

        canvas = Canvas(container, bg="#f0f2f5", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = Frame(canvas, bg="#f0f2f5")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas_window = canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw"
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        def update_frame_width(event=None):
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())

        canvas.bind('<Configure>', update_frame_width)
        canvas.pack(side=LEFT, fill=BOTH, expand=True, padx=0)
        scrollbar.pack(side=RIGHT, fill=Y)

        # Mousewheel binding
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

        self.window.bind("<MouseWheel>", on_mousewheel, add="+")
        self.window.bind("<Button-4>", on_mousewheel, add="+")
        self.window.bind("<Button-5>", on_mousewheel, add="+")
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        # Bottom close button
        button_frame = Frame(self.window, bg="#f0f2f5", height=60)
        button_frame.pack(fill=X, side=BOTTOM)
        button_frame.pack_propagate(False)

        close_btn = Button(
            button_frame,
            text="Close Dashboard",
            command=self.close,
            bg="#667eea",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            relief=FLAT,
            cursor="hand2",
            padx=30,
            pady=10,
            activebackground="#764ba2",
            activeforeground="white",
        )
        close_btn.pack(pady=10)

        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#764ba2"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#667eea"))

    def _cancel_pending_refresh(self) -> None:
        """Cancel any debounced refresh task scheduled via after()."""
        pending = self.dashboard_state.get('refresh_after_id')
        if pending is not None and self.window and self.window.winfo_exists():
            try:
                self.window.after_cancel(pending)
            except Exception:
                pass
            self.dashboard_state['refresh_after_id'] = None

    def schedule_refresh(self, delay_ms: int = 0, force_fetch: bool = False) -> None:
        """Schedule a dashboard refresh, optionally debounced."""
        self._cancel_pending_refresh()
        if not self.window or not self.window.winfo_exists():
            return

        if delay_ms > 0:
            self.dashboard_state['refresh_after_id'] = self.window.after(
                delay_ms, lambda: self.refresh_dashboard(force_fetch=force_fetch)
            )
        else:
            self.refresh_dashboard(force_fetch=force_fetch)

    def refresh_dashboard(self, force_fetch: bool = False) -> None:
        """Fetch records and render dashboard asynchronously."""
        self._cancel_pending_refresh()
        if not self.window or not self.window.winfo_exists():
            return

        self.dashboard_state['request_token'] += 1
        request_token = self.dashboard_state['request_token']
        criteria = {
            'date_range': self.filter_vars['date_range'].get(),
            'file_type': self.filter_vars['file_type'].get(),
            'search': self.filter_vars['search'].get(),
        }

        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        loading_frame = Frame(self.scrollable_frame, bg="white", relief=FLAT)
        loading_frame.pack(fill=BOTH, expand=True, padx=20, pady=50)
        Label(
            loading_frame,
            text="Loading statistics...",
            font=("Segoe UI", 14, "bold"),
            bg="white",
            fg="#667eea",
        ).pack(pady=(30, 10))

        if self.refresh_btn:
            self.refresh_btn.config(state=DISABLED, text="Refreshing...")

        def worker():
            try:
                use_cached = (
                    self.dashboard_state['records_cache'] is not None and not force_fetch
                )
                all_records = (
                    self.dashboard_state['records_cache']
                    if use_cached
                    else self.db.fetch_all_metadata()
                )
                all_types = sorted({r[4] for r in all_records if len(r) > 4 and r[4]})
                filtered = filter_records(all_records, criteria)
                stats = calculate_enhanced_stats(
                    filtered,
                    risk_analyzer_module=self.risk_analyzer,
                    risk_cache=self.dashboard_state['risk_cache'],
                )
                payload = (all_records, all_types, filtered, stats, None)
            except Exception as err:
                payload = (None, None, None, None, err)

            def apply_result():
                if not self.window or not self.window.winfo_exists():
                    return
                if request_token != self.dashboard_state['request_token']:
                    return

                if self.refresh_btn:
                    self.refresh_btn.config(state=NORMAL, text="⟳ Refresh")
                for widget in self.scrollable_frame.winfo_children():
                    widget.destroy()

                all_records, all_types, filtered, stats, error = payload
                if error is not None:
                    error_frame = Frame(self.scrollable_frame, bg="white", relief=FLAT)
                    error_frame.pack(fill=BOTH, expand=True, padx=20, pady=50)
                    Label(
                        error_frame,
                        text="Error Loading Statistics",
                        font=("Segoe UI", 16, "bold"),
                        bg="white",
                        fg="#e74c3c",
                    ).pack(pady=(30, 10))
                    Label(
                        error_frame,
                        text=str(error),
                        font=("Segoe UI", 11),
                        bg="white",
                        fg="#95a5a6",
                    ).pack(pady=(0, 30))
                    return

                self.dashboard_state['records_cache'] = all_records
                if self.type_combo:
                    self.type_combo['values'] = ["All Types"] + all_types

                if stats is None or stats['total'] == 0:
                    empty_frame = Frame(self.scrollable_frame, bg="white", relief=FLAT)
                    empty_frame.pack(fill=BOTH, expand=True, padx=20, pady=50)
                    Label(
                        empty_frame,
                        text="No matching data",
                        font=("Segoe UI", 16, "bold"),
                        bg="white",
                        fg="#888",
                    ).pack(pady=(30, 10))
                    Label(
                        empty_frame,
                        text="Adjust filters or extract more files!",
                        font=("Segoe UI", 12),
                        bg="white",
                        fg="#aaa",
                    ).pack(pady=(0, 30))
                    return

                self._render_dashboard_content(stats, filtered)

            if self.window and self.window.winfo_exists():
                self.window.after(0, apply_result)

        threading.Thread(target=worker, daemon=True).start()

    def _toggle_auto_refresh(self) -> None:
        """Toggle auto-refresh cycle every 30 seconds."""
        if self.filter_vars.get('auto_refresh') and self.filter_vars['auto_refresh'].get():
            def auto_update():
                if (
                    self.window
                    and self.window.winfo_exists()
                    and self.filter_vars['auto_refresh'].get()
                ):
                    self.schedule_refresh(force_fetch=True)
                    self.window.after(30000, auto_update)

            if self.window and self.window.winfo_exists():
                self.window.after(30000, auto_update)

    def _render_dashboard_content(self, stats: dict, filtered_records: list) -> None:
        """Render metrics cards, analytics charts, insights, and recent extractions."""
        # Row 1 cards
        cards_container1 = Frame(self.scrollable_frame, bg="#f0f2f5")
        cards_container1.pack(fill=X, padx=10, pady=(10, 8))
        cards_row1 = Frame(cards_container1, bg="#f0f2f5")
        cards_row1.pack(fill=X)

        create_metric_card(
            cards_row1,
            "Total Files",
            str(stats['total']),
            "Analyzed",
            "#667eea",
            "#764ba2",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=3)

        create_metric_card(
            cards_row1,
            "Total Size",
            format_size(stats['total_size']),
            "Storage",
            "#4facfe",
            "#00f2fe",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=3)

        create_metric_card(
            cards_row1,
            "File Types",
            str(len(stats['file_types'])),
            "Formats",
            "#43e97b",
            "#38f9d7",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=3)

        create_metric_card(
            cards_row1,
            "Average Size",
            format_size(stats['avg_size']),
            "Per File",
            "#fa709a",
            "#fee140",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=3)

        # Row 2 cards
        cards_container2 = Frame(self.scrollable_frame, bg="#f0f2f5")
        cards_container2.pack(fill=X, padx=10, pady=8)
        cards_row2 = Frame(cards_container2, bg="#f0f2f5")
        cards_row2.pack(fill=X)

        largest_name = (
            stats['max_size'][1][:20] + "..."
            if len(stats['max_size'][1]) > 20
            else stats['max_size'][1]
        )
        create_metric_card(
            cards_row2,
            "Largest File",
            format_size(stats['max_size'][0]),
            largest_name,
            "#f093fb",
            "#4facfe",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=3)

        smallest_name = (
            stats['min_size'][1][:20] + "..."
            if len(stats['min_size'][1]) > 20
            else stats['min_size'][1]
        )
        create_metric_card(
            cards_row2,
            "Smallest File",
            format_size(stats['min_size'][0]),
            smallest_name,
            "#764ba2",
            "#667eea",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=3)

        avg_per_day = stats['total'] / max(len(stats['files_by_date']), 1)
        create_metric_card(
            cards_row2,
            "Daily Average",
            f"{avg_per_day:.1f}",
            "Files/Day",
            "#30cfd0",
            "#667eea",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=3)

        most_common_type = (
            max(stats['file_types'].items(), key=lambda x: x[1])
            if stats['file_types']
            else ("N/A", 0)
        )
        create_metric_card(
            cards_row2,
            "Top Format",
            most_common_type[0],
            f"{most_common_type[1]} files",
            "#fa709a",
            "#764ba2",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=3)

        # Row 3 cards (Risk metrics)
        cards_container3 = Frame(self.scrollable_frame, bg="#f0f2f5")
        cards_container3.pack(fill=X, padx=10, pady=8)
        cards_row3 = Frame(cards_container3, bg="#f0f2f5")
        cards_row3.pack(fill=X)

        create_metric_card(
            cards_row3,
            "High Risk Files",
            str(stats['risk_counts'].get('HIGH', 0)),
            "Privacy alerts",
            "#e74c3c",
            "#c0392b",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=3)

        create_metric_card(
            cards_row3,
            "Medium Risk Files",
            str(stats['risk_counts'].get('MEDIUM', 0)),
            "Needs review",
            "#f39c12",
            "#d35400",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=3)

        create_metric_card(
            cards_row3,
            "Low Risk Files",
            str(stats['risk_counts'].get('LOW', 0)),
            "Safer metadata",
            "#27ae60",
            "#16a085",
        ).pack(side=LEFT, fill=BOTH, expand=True, padx=3)

        # Extended Analytics Charts
        charts_section = Frame(self.scrollable_frame, bg="#f0f2f5")
        charts_section.pack(fill=BOTH, expand=True, padx=10, pady=(8, 0))

        Label(
            charts_section,
            text="Extended Analytics",
            font=("Segoe UI", 14, "bold"),
            bg="#f0f2f5",
            fg="#2c3e50",
        ).pack(anchor=W, pady=(0, 10))

        charts_frame = Frame(charts_section, bg="white", relief=FLAT, bd=2)
        charts_frame.pack(fill=BOTH, expand=True)

        fig_width = max((self.window_w - 80) / 100, 12)
        fig = Figure(figsize=(fig_width, 5), facecolor='white')

        # Line chart for trends over time
        ax1 = fig.add_subplot(131)
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
        ax2 = fig.add_subplot(132)
        sizes_only = [s[0] for s in stats['file_sizes'] if s[0] > 0]
        if sizes_only:
            ax2.hist(sizes_only, bins=15, color='#43e97b', edgecolor='white', alpha=0.85)
            ax2.set_xlabel('File Size (bytes)', fontsize=9)
            ax2.set_ylabel('Count', fontsize=9)
            ax2.set_title('Size Distribution', fontsize=10, weight='bold', pad=10)
            ax2.grid(axis='y', alpha=0.2)

        # Top 5 files as horizontal bars
        ax3 = fig.add_subplot(133)
        if stats['largest_files']:
            top5 = stats['largest_files'][:5]
            names = [f[:20] + "..." if len(f) > 20 else f for _, f in top5]
            sizes = [s for s, _ in top5]
            y_pos = range(len(names))
            ax3.barh(
                y_pos,
                sizes,
                color=self.GRADIENT_COLORS[: len(names)],
                edgecolor='white',
                alpha=0.85,
            )
            ax3.set_yticks(y_pos)
            ax3.set_yticklabels(names, fontsize=8)
            ax3.set_xlabel('Size (bytes)', fontsize=9)
            ax3.set_title('Top 5 Largest Files', fontsize=10, weight='bold', pad=10)
            ax3.invert_yaxis()

        fig.tight_layout(pad=2)
        chart_canvas = FigureCanvasTkAgg(fig, master=charts_frame)
        chart_canvas.draw()
        chart_canvas.get_tk_widget().pack(fill=BOTH, expand=True, padx=10, pady=10)
        plt.close(fig)

        # Metadata Insights
        insights_section = Frame(self.scrollable_frame, bg="#f0f2f5")
        insights_section.pack(fill=X, padx=10, pady=(15, 0))

        Label(
            insights_section,
            text="Metadata Insights",
            font=("Segoe UI", 14, "bold"),
            bg="#f0f2f5",
            fg="#2c3e50",
        ).pack(anchor=W, pady=(0, 10))

        insights_frame = Frame(insights_section, bg="white", relief=FLAT, bd=2)
        insights_frame.pack(fill=X, padx=0, pady=0)

        insights_grid = Frame(insights_frame, bg="white")
        insights_grid.pack(fill=X, padx=20, pady=15)

        filenames = [r[2] for r in filtered_records if len(r) > 2]
        filename_counts = Counter(filenames)
        duplicates = {
            name: count for name, count in filename_counts.items() if count > 1
        }

        Label(
            insights_grid,
            text=f"Potential Duplicates: {len(duplicates)}",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#e74c3c" if duplicates else "#27ae60",
        ).grid(row=0, column=0, sticky=W, padx=10, pady=5)

        Label(
            insights_grid,
            text=f"Unique Files: {len(filename_counts)}",
            font=("Segoe UI", 11),
            bg="white",
            fg="#2c3e50",
        ).grid(row=0, column=1, sticky=W, padx=10, pady=5)

        complete_count = sum(
            1
            for r in filtered_records
            if len(r) >= 6 and all(r[i] for i in range(2, 6))
        )
        completeness = (
            (complete_count / stats['total'] * 100) if stats['total'] > 0 else 0
        )
        Label(
            insights_grid,
            text=f"Metadata Completeness: {completeness:.1f}%",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#27ae60" if completeness > 80 else "#f39c12",
        ).grid(row=0, column=2, sticky=W, padx=10, pady=5)

        # Recent extractions
        recent_section = Frame(self.scrollable_frame, bg="#f0f2f5")
        recent_section.pack(fill=X, padx=10, pady=(15, 15))

        Label(
            recent_section,
            text="Recent Extractions",
            font=("Segoe UI", 14, "bold"),
            bg="#f0f2f5",
            fg="#2c3e50",
        ).pack(anchor=W, pady=(0, 10))

        recent_frame = Frame(recent_section, bg="white", relief=FLAT, bd=2)
        recent_frame.pack(fill=X)

        recent = sorted(
            filtered_records,
            key=lambda x: x[5] if len(x) > 5 and x[5] else "",
            reverse=True,
        )[:5]

        for i, record in enumerate(recent, 1):
            filename = record[2] if len(record) > 2 else "Unknown"
            file_type = record[4] if len(record) > 4 else "Unknown"
            file_size = record[3] if len(record) > 3 else "0 B"
            display_name = (
                filename[:60] + '...' if len(filename) > 60 else filename
            )

            row_frame = Frame(recent_frame, bg="white", cursor="hand2")
            row_frame.pack(fill=X, padx=15, pady=8)

            badge = Label(
                row_frame,
                text=str(i),
                font=("Segoe UI", 10, "bold"),
                bg=self.GRADIENT_COLORS[i - 1],
                fg="white",
                width=3,
                height=1,
            )
            badge.pack(side=LEFT, padx=(0, 12))

            info_frame = Frame(row_frame, bg="white")
            info_frame.pack(side=LEFT, fill=X, expand=True)

            Label(
                info_frame,
                text=display_name,
                font=("Segoe UI", 10, "bold"),
                bg="white",
                fg="#2c3e50",
                anchor=W,
            ).pack(fill=X)

            Label(
                info_frame,
                text=f"{file_type} • {file_size}",
                font=("Segoe UI", 9),
                bg="white",
                fg="#7f8c8d",
                anchor=W,
            ).pack(fill=X)

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

    def close(self) -> None:
        """Safely destroy the dashboard window and cancel any pending timers."""
        self._cancel_pending_refresh()
        if self.window and self.window.winfo_exists():
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
