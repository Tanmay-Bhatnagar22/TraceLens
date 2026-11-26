"""TraceLens GUI tabs package.

Contains dedicated components for each notebook tab:
- ExtractorTab: File metadata extraction and viewer
- EditorTab: Metadata key-value editor
- HistoryTab: Historical metadata logs, searching, and exporting
- RiskTab: Privacy risk gauge and forensic timeline analysis
- PreviewTab: Formatted report generator and PDF image previewer
"""

from __future__ import annotations

from .editor_tab import EditorTab
from .extractor_tab import ExtractorTab
from .history_tab import HistoryTab
from .preview_tab import PreviewTab
from .risk_tab import RiskTab

__all__ = [
    "ExtractorTab",
    "EditorTab",
    "HistoryTab",
    "RiskTab",
    "PreviewTab",
]
