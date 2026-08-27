"""Data models and abstractions representing declarative risk rules and rulesets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RuleCondition:
    """Represents a single atomic condition or a composite boolean branch."""

    match_type: str = "key_contains"  # key_contains, key_regex, value_regex, value_contains, key_equals, exists
    keys: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    pattern: str = ""
    case_sensitive: bool = False
    any: list[RuleCondition] = field(default_factory=list)
    all: list[RuleCondition] = field(default_factory=list)
    none: list[RuleCondition] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | list[Any] | str) -> RuleCondition:
        """Parse condition tree from dictionary, list, or shorthand representation."""
        if isinstance(data, list):
            # List of conditions treated as ANY by default
            return cls(any=[cls.from_dict(item) for item in data])

        if isinstance(data, str):
            # Shorthand string treated as key_contains
            return cls(match_type="key_contains", keys=[data])

        if not isinstance(data, dict):
            return cls()

        # Check composite branches first
        any_branch = [cls.from_dict(c) for c in data.get("any", [])]
        all_branch = [cls.from_dict(c) for c in data.get("all", [])]
        none_branch = [cls.from_dict(c) for c in data.get("none", [])]

        raw_keys = data.get("keys", [])
        if isinstance(raw_keys, str):
            raw_keys = [raw_keys]
        elif not isinstance(raw_keys, list):
            raw_keys = []

        raw_tokens = data.get("tokens", [])
        if isinstance(raw_tokens, str):
            raw_tokens = [raw_tokens]
        elif not isinstance(raw_tokens, list):
            raw_tokens = []

        return cls(
            match_type=str(data.get("match_type", "key_contains")),
            keys=[str(k) for k in raw_keys],
            tokens=[str(t) for t in raw_tokens],
            pattern=str(data.get("pattern", "")),
            case_sensitive=bool(data.get("case_sensitive", False)),
            any=any_branch,
            all=all_branch,
            none=none_branch,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert condition to a dictionary for YAML serialization."""
        d: dict[str, Any] = {}
        if self.any:
            d["any"] = [c.to_dict() for c in self.any]
        if self.all:
            d["all"] = [c.to_dict() for c in self.all]
        if self.none:
            d["none"] = [c.to_dict() for c in self.none]
        if not (self.any or self.all or self.none):
            d["match_type"] = self.match_type
            if self.keys:
                d["keys"] = self.keys
            if self.tokens:
                d["tokens"] = self.tokens
            if self.pattern:
                d["pattern"] = self.pattern
            if self.case_sensitive:
                d["case_sensitive"] = self.case_sensitive
        return d


@dataclass
class RiskRuleDefinition:
    """Represents a discrete risk assessment rule configured via YAML or code."""

    id: str
    name: str = ""
    category: str = "privacy"
    score: int = 10
    severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    enabled: bool = True
    reason: str = ""
    remediation: str = ""
    condition: RuleCondition = field(default_factory=RuleCondition)
    checker: Callable[[dict[str, Any]], bool] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskRuleDefinition:
        cond_data = data.get("conditions", data.get("condition", {}))
        return cls(
            id=str(data.get("id", data.get("name", "unnamed_rule"))),
            name=str(data.get("name", data.get("id", "Unnamed Rule"))),
            category=str(data.get("category", "privacy")),
            score=int(data.get("score", 10)),
            severity=str(data.get("severity", "MEDIUM")).upper(),
            enabled=bool(data.get("enabled", True)),
            reason=str(data.get("reason", "")),
            remediation=str(data.get("remediation", "")),
            condition=RuleCondition.from_dict(cond_data),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "score": self.score,
            "severity": self.severity,
            "enabled": self.enabled,
            "reason": self.reason,
            "remediation": self.remediation,
            "conditions": self.condition.to_dict(),
        }


@dataclass
class AnomalyRuleDefinition:
    """Represents an anomaly detection heuristic configured via YAML."""

    id: str
    name: str = ""
    description: str = ""
    enabled: bool = True
    penalty: int = 20
    template: str = ""
    message: str = ""
    software_keys: list[str] = field(default_factory=lambda: ["software", "application", "producer", "editor"])
    min_distinct: int = 2
    block_keys: list[str] = field(
        default_factory=lambda: ["xmp", "iptc", "exif", "makernote", "thumbnail", "history"]
    )
    min_count: int = 3

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnomalyRuleDefinition:
        return cls(
            id=str(data.get("id", "anomaly")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            enabled=bool(data.get("enabled", True)),
            penalty=int(data.get("penalty", 20)),
            template=str(data.get("template", "")),
            message=str(data.get("message", "")),
            software_keys=list(data.get("software_keys", ["software", "application", "producer", "editor"])),
            min_distinct=int(data.get("min_distinct", 2)),
            block_keys=list(
                data.get("block_keys", ["xmp", "iptc", "exif", "makernote", "thumbnail", "history"])
            ),
            min_count=int(data.get("min_count", 3)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "penalty": self.penalty,
            "template": self.template,
            "message": self.message,
            "software_keys": self.software_keys,
            "min_distinct": self.min_distinct,
            "block_keys": self.block_keys,
            "min_count": self.min_count,
        }


@dataclass
class ThresholdConfig:
    """Score boundaries and labels."""

    low_min: int = 0
    low_max: int = 29
    low_label: str = "LOW"
    medium_min: int = 30
    medium_max: int = 64
    medium_label: str = "MEDIUM"
    high_min: int = 65
    high_max: int = 100
    high_label: str = "HIGH"

    def to_levels_tuple(self) -> tuple[tuple[int, int, str], ...]:
        return (
            (self.low_min, self.low_max, self.low_label),
            (self.medium_min, self.medium_max, self.medium_label),
            (self.high_min, self.high_max, self.high_label),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThresholdConfig:
        low = data.get("low", {})
        medium = data.get("medium", {})
        high = data.get("high", {})

        return cls(
            low_min=int(low.get("min", 0)),
            low_max=int(low.get("max", 29)),
            low_label=str(low.get("label", "LOW")),
            medium_min=int(medium.get("min", 30)),
            medium_max=int(medium.get("max", 64)),
            medium_label=str(medium.get("label", "MEDIUM")),
            high_min=int(high.get("min", 65)),
            high_max=int(high.get("max", 100)),
            high_label=str(high.get("label", "HIGH")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "low": {"min": self.low_min, "max": self.low_max, "label": self.low_label},
            "medium": {"min": self.medium_min, "max": self.medium_max, "label": self.medium_label},
            "high": {"min": self.high_min, "max": self.high_max, "label": self.high_label},
        }


@dataclass
class TimelineConfig:
    """Configuration for timestamp extraction candidates and format parsers."""

    candidate_keys: list[str] = field(
        default_factory=lambda: [
            "capture",
            "created",
            "creation",
            "modified",
            "edit",
            "timestamp",
            "date",
            "time",
            "last saved",
        ]
    )
    datetime_formats: list[str] = field(
        default_factory=lambda: [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%Y-%m-%d",
            "%d-%m-%Y",
        ]
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimelineConfig:
        cand = data.get("candidate_keys")
        fmts = data.get("datetime_formats")
        return cls(
            candidate_keys=list(cand) if isinstance(cand, list) else [
                "capture", "created", "creation", "modified", "edit", "timestamp", "date", "time", "last saved"
            ],
            datetime_formats=list(fmts) if isinstance(fmts, list) else [
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d", "%d-%m-%Y"
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_keys": self.candidate_keys,
            "datetime_formats": self.datetime_formats,
        }


@dataclass
class RuleSet:
    """Aggregated container for all rules, thresholds, timeline settings, and anomaly rules."""

    version: str = "1.0"
    name: str = "TraceLens Default Ruleset"
    description: str = "Metadata privacy risk and forensic inspection ruleset"
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    scoring: dict[str, Any] = field(default_factory=lambda: {"max_score": 100, "anomaly_penalty": 20})
    timeline: TimelineConfig = field(default_factory=TimelineConfig)
    anomalies: list[AnomalyRuleDefinition] = field(default_factory=list)
    rules: list[RiskRuleDefinition] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleSet:
        version = str(data.get("version", "1.0"))
        name = str(data.get("name", "TraceLens Default Ruleset"))
        desc = str(data.get("description", ""))

        thresholds = ThresholdConfig.from_dict(data.get("thresholds", {}))
        scoring = dict(data.get("scoring", {"max_score": 100, "anomaly_penalty": 20}))
        timeline = TimelineConfig.from_dict(data.get("timeline", {}))

        anomalies_data = data.get("anomalies", [])
        anomalies = [AnomalyRuleDefinition.from_dict(a) for a in anomalies_data if isinstance(a, dict)]

        rules_data = data.get("rules", [])
        rules = [RiskRuleDefinition.from_dict(r) for r in rules_data if isinstance(r, dict)]

        return cls(
            version=version,
            name=name,
            description=desc,
            thresholds=thresholds,
            scoring=scoring,
            timeline=timeline,
            anomalies=anomalies,
            rules=rules,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "thresholds": self.thresholds.to_dict(),
            "scoring": self.scoring,
            "timeline": self.timeline.to_dict(),
            "anomalies": [a.to_dict() for a in self.anomalies],
            "rules": [r.to_dict() for r in self.rules],
        }
