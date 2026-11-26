"""Privacy and Forensic Risk Analyzer facade.

Powered by the YAML-driven RiskEngine while maintaining complete backward compatibility.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from src.config.logging_config import get_logger
from src.core.risk.risk_engine import RiskEngine
from src.core.risk.rule_models import RiskRuleDefinition, RuleCondition, RuleSet

logger = get_logger("core.risk")


@dataclass
class RiskRule:
    """Legacy RiskRule model preserved for backward compatibility with older callers/extensions."""

    name: str
    score: int
    reason: str
    checker: Callable[[dict[str, Any]], bool]


class PrivacyForensicAnalyzer:
    """Combined privacy risk scanner + forensic timeline generator.

    Provides high-level risk evaluation powered by the underlying YAML-driven RiskEngine.
    """

    RISK_LEVELS = (
        (0, 29, "LOW"),
        (30, 64, "MEDIUM"),
        (65, 100, "HIGH"),
    )

    def __init__(
        self,
        ruleset: RuleSet | None = None,
        rules_path: str | Path | None = None,
    ) -> None:
        self.engine = RiskEngine(ruleset=ruleset, rules_path=rules_path)

    @property
    def rules(self) -> list[Any]:
        """Provides a compatible list of rules.

        Legacy code appending to `self.rules` will have their checker registered.
        """
        return self.engine.rules

    @rules.setter
    def rules(self, new_rules: list[Any]) -> None:
        converted: list[RiskRuleDefinition] = []
        for r in new_rules:
            if isinstance(r, RiskRuleDefinition):
                converted.append(r)
            elif isinstance(r, RiskRule):
                converted.append(
                    RiskRuleDefinition(
                        id=r.name,
                        name=r.name.replace("_", " ").title(),
                        score=r.score,
                        reason=r.reason,
                        checker=r.checker,
                    )
                )
            elif hasattr(r, "checker"):
                converted.append(
                    RiskRuleDefinition(
                        id=getattr(r, "name", "rule"),
                        name=getattr(r, "name", "rule"),
                        score=getattr(r, "score", 10),
                        reason=getattr(r, "reason", ""),
                        checker=getattr(r, "checker"),
                    )
                )
        self.engine.ruleset.rules = converted

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze_file(
        self,
        metadata: dict[str, Any] | None,
        file_path: str | None = None,
        fallback_timestamps: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate privacy and forensic risk for a metadata dictionary."""
        return self.engine.analyze_file(
            metadata=metadata,
            file_path=file_path,
            fallback_timestamps=fallback_timestamps,
        )

    def analyze_batch(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze a list of file entries and build folder-level summary.

        Each entry expects keys: `file_path` and `metadata`.
        """
        return self.engine.analyze_batch(entries)

    def build_timeline(
        self,
        metadata: dict[str, Any],
        fallback_timestamps: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Construct chronological timeline from metadata timestamps."""
        return self.engine.build_timeline(metadata, fallback_timestamps=fallback_timestamps)

    def detect_anomalies(
        self,
        metadata: dict[str, Any],
        timeline: list[dict[str, Any]],
    ) -> list[str]:
        """Detect timestamp or editing irregularities."""
        return self.engine.detect_anomalies(metadata, timeline)

    def load_rules_from_yaml(self, file_path: str | Path) -> None:
        """Dynamically load an external YAML ruleset."""
        self.engine.load_rules_file(file_path)

    # ------------------------------------------------------------------
    # Legacy helper shims
    # ------------------------------------------------------------------
    def _score_to_level(self, score: int) -> str:
        return self.engine._score_to_level(score)

    def _has_any_key(self, metadata: dict[str, Any], keywords: list[str]) -> bool:
        return self.engine._has_key_containing(metadata, keywords)

    def _has_gps_coordinates(self, metadata: dict[str, Any]) -> bool:
        cond = RuleCondition(
            any=[
                RuleCondition(match_type="key_contains", keys=["gps", "latitude", "longitude", "lat", "lon", "location"]),
                RuleCondition(match_type="value_regex", pattern=r"[-+]?\d{1,3}\.\d+\s*,\s*[-+]?\d{1,3}\.\d+"),
            ]
        )
        return self.engine.evaluate_condition(cond, metadata)

    def _extract_timestamp_candidates(self, metadata: dict[str, Any]) -> list[tuple[str, str, datetime]]:
        return self.engine._extract_timestamp_candidates(metadata)

    def _parse_datetime(self, value: Any) -> datetime | None:
        return self.engine._parse_datetime(value)


# Global singleton instance
_analyzer = PrivacyForensicAnalyzer()
analyzer = _analyzer


def analyze_metadata(
    metadata: dict[str, Any] | None,
    file_path: str | None = None,
    fallback_timestamps: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Top-level convenience function analyzing metadata dictionary."""
    return _analyzer.analyze_file(metadata, file_path, fallback_timestamps=fallback_timestamps)


def analyze_batch(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Top-level convenience function analyzing batch entries."""
    return _analyzer.analyze_batch(entries)
