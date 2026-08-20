"""TraceLens GUI package."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from .gui import MetadataAnalyzerApp, run_gui
from .statistics_dashboard import (
    StatisticsDashboard,
    create_metric_card,
    open_statistics_dashboard,
)
from .tabs import (
    EditorTab,
    ExtractorTab,
    HistoryTab,
    PreviewTab,
    RiskTab,
)

__all__ = [
    "MetadataAnalyzerApp",
    "run_gui",
    "StatisticsDashboard",
    "open_statistics_dashboard",
    "create_metric_card",
    "ExtractorTab",
    "EditorTab",
    "HistoryTab",
    "RiskTab",
    "PreviewTab",
]
