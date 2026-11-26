"""Domain models for report generation and exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReportConfig:
    """Configuration options for report generation."""

    title: str = "Metadata Analysis Report"
    file_path: str = ""
    output_path: str = ""
    format: str = "pdf"  # pdf, json, xml, csv, txt, excel
    include_risk: bool = True
    include_timeline: bool = True
    include_raw_metadata: bool = True
    batch_mode: bool = False
    custom_notes: str = ""


@dataclass
class ReportResult:
    """Outcome of a report generation or data export operation."""

    success: bool
    output_path: str = ""
    format: str = "pdf"
    message: str = ""
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert report result to a dictionary."""
        return {
            "success": self.success,
            "output_path": self.output_path,
            "format": self.format,
            "message": self.message,
            "size_bytes": self.size_bytes,
        }
