"""Risk analysis service for forensic timeline analysis and privacy risk assessment."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from src.config.logging_config import get_logger
from src.core.risk import (
    PrivacyForensicAnalyzer,
    RiskEngine,
    RiskRuleDefinition,
    analyzer as default_analyzer,
)
from src.models.risk import BatchRiskResult, RiskAssessment

logger = get_logger("core.services.risk")


class RiskAnalysisService:
    """Application service for assessing metadata privacy vulnerabilities and forensic risks."""

    def __init__(
        self,
        analyzer: PrivacyForensicAnalyzer | RiskEngine | None = None,
    ) -> None:
        self.analyzer = analyzer or default_analyzer

    @property
    def engine(self) -> RiskEngine:
        """Accessor for the underlying RiskEngine instance."""
        if isinstance(self.analyzer, RiskEngine):
            return self.analyzer
        if hasattr(self.analyzer, "engine"):
            return self.analyzer.engine
        # Fallback create wrapper
        return RiskEngine()

    def load_custom_rules(self, rules_path: str | Path) -> None:
        """Load an external YAML ruleset into the active engine."""
        self.engine.load_rules_file(rules_path)

    def get_active_rules(self) -> list[RiskRuleDefinition]:
        """Return the list of currently registered risk rules."""
        return self.engine.rules

    def export_rules_yaml(self, file_path: str | Path | None = None) -> str:
        """Export current ruleset configuration as YAML."""
        return self.engine.export_rules_yaml(file_path=file_path)

    def analyze_metadata(
        self,
        metadata: dict[str, Any] | None,
        file_path: str | None = None,
        fallback_timestamps: dict[str, Any] | None = None,
    ) -> RiskAssessment:
        """Evaluate privacy and forensic risk for a given metadata dictionary.

        Args:
            metadata: Metadata dictionary to analyze.
            file_path: Optional path to the associated file.
            fallback_timestamps: Optional timestamp fallback dictionary.

        Returns:
            RiskAssessment domain model.
        """
        raw_result = self.analyzer.analyze_file(
            metadata=metadata,
            file_path=file_path,
            fallback_timestamps=fallback_timestamps,
        )

        # Identify specific sensitive fields found if not already present
        if "sensitive_keys" not in raw_result or not raw_result["sensitive_keys"]:
            sensitive = self.identify_sensitive_fields(metadata or {})
            raw_result["sensitive_keys"] = sensitive

        return RiskAssessment.from_dict(raw_result)

    def analyze_batch(
        self,
        records: Iterable[dict[str, Any] | tuple[Any, ...]],
    ) -> BatchRiskResult:
        """Perform batch risk analysis across multiple records or database rows.

        Args:
            records: List/iterable of metadata dictionaries or database row tuples.

        Returns:
            BatchRiskResult domain model.
        """
        assessments: list[RiskAssessment] = []
        high = 0
        medium = 0
        low = 0
        total_score = 0

        for item in records:
            if isinstance(item, tuple):
                # Format: (id, file_path, file_name, size, type, extracted_at, modified_on, full_metadata)
                file_path = item[1] if len(item) > 1 else ""
                raw_meta = item[7] if len(item) > 7 else "{}"
                if isinstance(raw_meta, str):
                    try:
                        meta_dict = json.loads(raw_meta)
                    except Exception:
                        meta_dict = {}
                elif isinstance(raw_meta, dict):
                    meta_dict = raw_meta
                else:
                    meta_dict = {}
                fallback = {
                    "Extracted At": item[5] if len(item) > 5 else "",
                    "Modified On": item[6] if len(item) > 6 else "",
                }
            elif isinstance(item, dict):
                file_path = item.get("file_path", "")
                meta_dict = item.get("metadata", item.get("full_metadata", item))
                fallback = item.get("fallback_timestamps")
            else:
                continue

            assessment = self.analyze_metadata(
                metadata=meta_dict if isinstance(meta_dict, dict) else {},
                file_path=file_path,
                fallback_timestamps=fallback,
            )
            assessments.append(assessment)

            total_score += assessment.risk_score
            if assessment.risk_level == "HIGH":
                high += 1
            elif assessment.risk_level == "MEDIUM":
                medium += 1
            else:
                low += 1

        total = len(assessments)
        avg = (total_score / total) if total > 0 else 0.0

        return BatchRiskResult(
            total_analyzed=total,
            high_risk_count=high,
            medium_risk_count=medium,
            low_risk_count=low,
            avg_risk_score=avg,
            assessments=assessments,
        )

    def identify_sensitive_fields(self, metadata: dict[str, Any]) -> list[str]:
        """Find keys in metadata containing sensitive indicators (GPS, Author, Serial, etc.)."""
        if hasattr(self.engine, "identify_sensitive_fields"):
            return self.engine.identify_sensitive_fields(metadata)

        sensitive_patterns = [
            "gps", "latitude", "longitude", "altitude",
            "author", "creator", "owner", "user", "last modified by",
            "serial", "imei", "device", "camera", "model", "make",
            "software", "producer", "history", "xmp", "exif", "iptc"
        ]

        found_keys = []
        for key in metadata.keys():
            k_lower = str(key).lower()
            if any(pat in k_lower for pat in sensitive_patterns):
                found_keys.append(str(key))

        return sorted(found_keys)

    def get_remediation_suggestions(self, assessment: RiskAssessment) -> list[str]:
        """Generate actionable recommendations to remediate discovered risks."""
        suggestions: list[str] = []

        if assessment.risk_score == 0:
            return ["No high-sensitivity metadata detected. File is safe for public distribution."]

        # Check for GPS
        if any("gps" in reason.lower() or "location" in reason.lower() for reason in assessment.reasons):
            suggestions.append("Strip GPS/geotag coordinates before sharing to prevent physical location exposure.")

        # Check for Author/User
        if any("author" in reason.lower() or "user" in reason.lower() or "identity" in reason.lower() for reason in assessment.reasons):
            suggestions.append("Remove creator, author, and user account metadata to protect personal identity.")

        # Check for Device/Camera
        if any("device" in reason.lower() or "camera" in reason.lower() for reason in assessment.reasons):
            suggestions.append("Clear device serial numbers, camera model, and hardware identifiers.")

        # Check for Software/Editor traces
        if any("software" in reason.lower() or "editor" in reason.lower() or "traces" in reason.lower() for reason in assessment.reasons):
            suggestions.append("Scrub editing software versions and revision history from document headers.")

        # Check for Anomalies
        if assessment.anomalies:
            suggestions.append("Investigate timeline anomalies (e.g. modification timestamp earlier than creation timestamp).")

        if not suggestions:
            suggestions.append("Consider sanitizing all metadata tags prior to public distribution.")

        return suggestions
