"""Domain models for risk assessment and forensic analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RiskAssessment:
    """Represents the privacy and forensic risk assessment for a file."""

    file_path: str = ""
    file_name: str = ""
    risk_score: int = 0
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH
    reasons: list[str] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    sensitive_keys: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskAssessment:
        """Create a RiskAssessment instance from an analyzer dictionary."""
        return cls(
            file_path=data.get("file_path", ""),
            file_name=data.get("file_name", ""),
            risk_score=int(data.get("risk_score", 0)),
            risk_level=str(data.get("risk_level", "LOW")),
            reasons=list(data.get("reasons", [])),
            timeline=list(data.get("timeline", [])),
            anomalies=list(data.get("anomalies", [])),
            sensitive_keys=list(data.get("sensitive_keys", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert risk assessment to a dictionary."""
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "reasons": self.reasons,
            "timeline": self.timeline,
            "anomalies": self.anomalies,
            "sensitive_keys": self.sensitive_keys,
        }


@dataclass
class BatchRiskResult:
    """Represents aggregated risk assessment results across multiple files."""

    total_analyzed: int = 0
    high_risk_count: int = 0
    medium_risk_count: int = 0
    low_risk_count: int = 0
    avg_risk_score: float = 0.0
    assessments: list[RiskAssessment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert batch risk result to a dictionary."""
        return {
            "total_analyzed": self.total_analyzed,
            "high_risk_count": self.high_risk_count,
            "medium_risk_count": self.medium_risk_count,
            "low_risk_count": self.low_risk_count,
            "avg_risk_score": round(self.avg_risk_score, 2),
            "assessments": [a.to_dict() for a in self.assessments],
        }
