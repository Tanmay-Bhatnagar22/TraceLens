"""Domain models for statistical analytics and dashboard summaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalyticsSummary:
    """Aggregated statistical metrics and metadata intelligence."""

    total_files: int = 0
    total_size_bytes: int = 0
    total_size_formatted: str = "0.0 B"
    avg_size_formatted: str = "0.0 B"
    file_type_counts: dict[str, int] = field(default_factory=dict)
    risk_distribution: dict[str, int] = field(default_factory=lambda: {"HIGH": 0, "MEDIUM": 0, "LOW": 0})
    avg_risk_score: float = 0.0
    top_threats: list[dict[str, Any]] = field(default_factory=list)
    recent_activity: list[dict[str, Any]] = field(default_factory=list)
    timeline_events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert analytics summary to dictionary."""
        return {
            "total_files": self.total_files,
            "total_size_bytes": self.total_size_bytes,
            "total_size_formatted": self.total_size_formatted,
            "avg_size_formatted": self.avg_size_formatted,
            "file_type_counts": self.file_type_counts,
            "risk_distribution": self.risk_distribution,
            "avg_risk_score": round(self.avg_risk_score, 2),
            "top_threats": self.top_threats,
            "recent_activity": self.recent_activity,
            "timeline_events": self.timeline_events,
        }
