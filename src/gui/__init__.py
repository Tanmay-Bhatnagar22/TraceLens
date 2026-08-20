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
    open_statistics_dashboard,
    create_metric_card,
)

__all__ = [
    "MetadataAnalyzerApp",
    "run_gui",
    "StatisticsDashboard",
    "open_statistics_dashboard",
    "create_metric_card",
]


