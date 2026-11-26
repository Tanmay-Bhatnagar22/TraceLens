"""YAML-driven risk analysis and forensic inspection engine for TraceLens."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Pattern

from src.config.logging_config import get_logger
from src.core.risk.rule_models import (
    AnomalyRuleDefinition,
    RiskRuleDefinition,
    RuleCondition,
    RuleSet,
    ThresholdConfig,
    TimelineConfig,
)
from src.core.risk.yaml_parser import dump_yaml, load_yaml_file, load_yaml_string

logger = get_logger("core.risk.engine")

DEFAULT_RULES_PATH = Path(__file__).parent / "rules.yaml"


class RiskEngine:
    """Core risk engine orchestrating declarative YAML rule evaluation,

    forensic timeline construction, anomaly detection, and remediation generation.
    """

    def __init__(
        self,
        ruleset: RuleSet | None = None,
        rules_path: str | Path | None = None,
    ) -> None:
        self._regex_cache: dict[str, Pattern[str]] = {}
        self.rules_path: Path | None = None

        if ruleset is not None:
            self.ruleset = ruleset
        elif rules_path is not None:
            self.load_rules_file(rules_path)
        else:
            if DEFAULT_RULES_PATH.is_file():
                try:
                    self.load_rules_file(DEFAULT_RULES_PATH)
                except Exception as exc:
                    logger.warning("Failed to load default rules from %s: %s. Using fallback.", DEFAULT_RULES_PATH, exc)
                    self.ruleset = self._create_fallback_ruleset()
            else:
                self.ruleset = self._create_fallback_ruleset()

    # ------------------------------------------------------------------
    # Rule Management & YAML Integration
    # ------------------------------------------------------------------
    def load_rules_file(self, file_path: str | Path) -> None:
        """Load and compile rules from a YAML file."""
        p = Path(file_path)
        data = load_yaml_file(p)
        self.ruleset = RuleSet.from_dict(data)
        self.rules_path = p
        self._regex_cache.clear()
        logger.info("Loaded %d risk rules from %s", len(self.ruleset.rules), p)

    def load_rules_yaml(self, yaml_text: str) -> None:
        """Load and compile rules from a YAML string."""
        data = load_yaml_string(yaml_text)
        self.ruleset = RuleSet.from_dict(data)
        self._regex_cache.clear()
        logger.info("Loaded %d risk rules from YAML string", len(self.ruleset.rules))

    def reload_default_rules(self) -> None:
        """Reload the default ruleset from disk or fallback."""
        if DEFAULT_RULES_PATH.is_file():
            self.load_rules_file(DEFAULT_RULES_PATH)
        else:
            self.ruleset = self._create_fallback_ruleset()

    def export_rules_yaml(self, file_path: str | Path | None = None) -> str:
        """Export current ruleset to a YAML string or file."""
        data = self.ruleset.to_dict()
        return dump_yaml(data, file_path=file_path)

    def add_rule(self, rule: RiskRuleDefinition) -> None:
        """Add or overwrite a rule in the active ruleset."""
        for idx, existing in enumerate(self.ruleset.rules):
            if existing.id == rule.id:
                self.ruleset.rules[idx] = rule
                return
        self.ruleset.rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID. Returns True if removed, False if not found."""
        initial_len = len(self.ruleset.rules)
        self.ruleset.rules = [r for r in self.ruleset.rules if r.id != rule_id]
        return len(self.ruleset.rules) < initial_len

    def enable_rule(self, rule_id: str, enabled: bool = True) -> bool:
        """Enable or disable a specific rule by ID."""
        for rule in self.ruleset.rules:
            if rule.id == rule_id:
                rule.enabled = enabled
                return True
        return False

    def get_rule(self, rule_id: str) -> RiskRuleDefinition | None:
        """Retrieve a rule definition by ID."""
        for rule in self.ruleset.rules:
            if rule.id == rule_id:
                return rule
        return None

    @property
    def rules(self) -> list[RiskRuleDefinition]:
        """Accessor for active rules list."""
        return self.ruleset.rules

    # ------------------------------------------------------------------
    # Analysis & Evaluation API
    # ------------------------------------------------------------------
    def analyze_file(
        self,
        metadata: dict[str, Any] | None,
        file_path: str | None = None,
        fallback_timestamps: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform comprehensive privacy and forensic risk assessment on file metadata.

        Args:
            metadata: Metadata dictionary.
            file_path: Optional path to the analyzed file.
            fallback_timestamps: Optional timestamp fallbacks if metadata lacks dates.

        Returns:
            Dictionary matching the standard TraceLens risk assessment schema.
        """
        metadata = metadata if isinstance(metadata, dict) else {}
        matched_rules: list[RiskRuleDefinition] = []
        score = 0

        # Evaluate rules
        for rule in self.ruleset.rules:
            if not rule.enabled:
                continue

            try:
                matched = False
                if rule.checker is not None:
                    matched = bool(rule.checker(metadata))
                else:
                    matched = self.evaluate_condition(rule.condition, metadata)

                if matched:
                    matched_rules.append(rule)
                    score += rule.score
            except Exception as exc:
                logger.debug("Error evaluating rule '%s': %s", rule.id, exc)
                continue

        # Build timeline and detect anomalies
        timeline = self.build_timeline(metadata, fallback_timestamps=fallback_timestamps)
        anomalies = self.detect_anomalies(metadata, timeline)

        # Anomaly penalties
        if anomalies:
            penalty = int(self.ruleset.scoring.get("anomaly_penalty", 20))
            score += penalty

        # Cap score
        max_score = int(self.ruleset.scoring.get("max_score", 100))
        score = min(score, max_score)
        level = self._score_to_level(score)

        # Build reason strings
        reasons = [rule.reason for rule in matched_rules if rule.reason]
        reasons.extend(anomalies)
        if not reasons:
            reasons = ["No high-sensitivity metadata indicators were detected."]

        # Identify sensitive keys and remediation recommendations
        sensitive_keys = self.identify_sensitive_fields(metadata)
        remediations = self.get_remediation_suggestions(matched_rules, anomalies)

        logger.debug(
            "Risk analysis for %s: score=%d (%s), matched=%d, anomalies=%d",
            file_path or "unnamed",
            score,
            level,
            len(matched_rules),
            len(anomalies),
        )

        return {
            "file_path": file_path or "",
            "file_name": os.path.basename(file_path) if file_path else "",
            "risk_score": score,
            "risk_level": level,
            "reasons": reasons,
            "matched_rules": [rule.id for rule in matched_rules],
            "timeline": timeline,
            "anomalies": anomalies,
            "event_count": len(timeline),
            "sensitive_keys": sensitive_keys,
            "remediation_suggestions": remediations,
        }

    def analyze_batch(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze multiple file entries and compute aggregate folder/batch metrics.

        Each entry expects: `file_path` and `metadata`.
        """
        results: list[dict[str, Any]] = []
        risk_counts = {
            self.ruleset.thresholds.low_label: 0,
            self.ruleset.thresholds.medium_label: 0,
            self.ruleset.thresholds.high_label: 0,
        }
        folder_stats: dict[str, dict[str, int]] = {}

        for entry in entries:
            file_path = entry.get("file_path", "")
            metadata = entry.get("metadata", {})
            item = self.analyze_file(metadata, file_path)
            results.append(item)

            lvl = item["risk_level"]
            risk_counts[lvl] = risk_counts.get(lvl, 0) + 1

            folder = os.path.dirname(file_path) if file_path else "Unknown"
            if folder not in folder_stats:
                folder_stats[folder] = {
                    "total": 0,
                    self.ruleset.thresholds.low_label: 0,
                    self.ruleset.thresholds.medium_label: 0,
                    self.ruleset.thresholds.high_label: 0,
                }
            folder_stats[folder]["total"] += 1
            folder_stats[folder][lvl] = folder_stats[folder].get(lvl, 0) + 1

        highest = max(results, key=lambda x: x["risk_score"], default=None)
        return {
            "total_files": len(results),
            "risk_counts": risk_counts,
            "folders": folder_stats,
            "highest_risk": highest,
            "results": results,
        }

    # ------------------------------------------------------------------
    # Condition Matching Logic
    # ------------------------------------------------------------------
    def evaluate_condition(self, condition: RuleCondition, metadata: dict[str, Any]) -> bool:
        """Evaluate a condition tree against metadata."""
        if condition.any:
            return any(self.evaluate_condition(c, metadata) for c in condition.any)

        if condition.all:
            return all(self.evaluate_condition(c, metadata) for c in condition.all)

        if condition.none:
            return not any(self.evaluate_condition(c, metadata) for c in condition.none)

        mtype = condition.match_type

        if mtype in ("key_contains", "key_matches"):
            tokens = condition.keys or condition.tokens
            return self._has_key_containing(metadata, tokens, case_sensitive=condition.case_sensitive)

        if mtype in ("value_contains", "value_matches"):
            tokens = condition.tokens or condition.keys
            return self._has_value_containing(metadata, tokens, case_sensitive=condition.case_sensitive)

        if mtype == "value_regex":
            if not condition.pattern:
                return False
            pattern = self._get_compiled_regex(condition.pattern, condition.case_sensitive)
            for val in metadata.values():
                if pattern.search(str(val)):
                    return True
            return False

        if mtype == "key_regex":
            if not condition.pattern:
                return False
            pattern = self._get_compiled_regex(condition.pattern, condition.case_sensitive)
            for k in metadata.keys():
                if pattern.search(str(k)):
                    return True
            return False

        if mtype == "key_equals":
            target_keys = {k if condition.case_sensitive else k.lower() for k in (condition.keys or condition.tokens)}
            for k in metadata.keys():
                k_val = str(k) if condition.case_sensitive else str(k).lower()
                if k_val in target_keys:
                    return True
            return False

        if mtype == "exists":
            target_keys = {k if condition.case_sensitive else k.lower() for k in (condition.keys or condition.tokens)}
            for k, v in metadata.items():
                k_val = str(k) if condition.case_sensitive else str(k).lower()
                if k_val in target_keys and v not in (None, "", [], {}):
                    return True
            return False

        # Fallback to key contains
        tokens = condition.keys or condition.tokens
        if tokens:
            return self._has_key_containing(metadata, tokens, case_sensitive=condition.case_sensitive)

        return False

    def identify_sensitive_fields(self, metadata: dict[str, Any]) -> list[str]:
        """Find keys in metadata matching sensitive criteria."""
        found_keys: set[str] = set()

        for rule in self.ruleset.rules:
            if not rule.enabled:
                continue

            # Check each metadata key individually against the rule condition
            for key, val in metadata.items():
                single_meta = {key: val}
                try:
                    if rule.checker is not None:
                        if rule.checker(single_meta):
                            found_keys.add(str(key))
                    elif self.evaluate_condition(rule.condition, single_meta):
                        found_keys.add(str(key))
                except Exception:
                    continue

        return sorted(list(found_keys))

    def get_remediation_suggestions(
        self,
        matched_rules: list[RiskRuleDefinition],
        anomalies: list[str],
    ) -> list[str]:
        """Generate remediation recommendations based on matched rules and discovered anomalies."""
        if not matched_rules and not anomalies:
            return ["No high-sensitivity metadata detected. File is safe for public distribution."]

        suggestions: list[str] = []
        for r in matched_rules:
            if r.remediation and r.remediation not in suggestions:
                suggestions.append(r.remediation)

        if anomalies:
            anom_sugg = "Investigate timeline anomalies (e.g. modification timestamp earlier than creation timestamp)."
            if anom_sugg not in suggestions:
                suggestions.append(anom_sugg)

        if not suggestions:
            suggestions.append("Consider sanitizing all metadata tags prior to public distribution.")

        return suggestions

    # ------------------------------------------------------------------
    # Timeline & Anomaly Detection
    # ------------------------------------------------------------------
    def build_timeline(
        self,
        metadata: dict[str, Any],
        fallback_timestamps: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Extract and sort chronological metadata timeline events."""
        candidates = self._extract_timestamp_candidates(metadata)

        if not candidates and isinstance(fallback_timestamps, dict):
            for key, value in fallback_timestamps.items():
                dt_obj = self._parse_datetime(value)
                if dt_obj is None:
                    continue
                candidates.append((str(key), str(value), dt_obj))

        timeline = []
        for key, value, dt_obj in candidates:
            timeline.append(
                {
                    "event": key,
                    "timestamp": value,
                    "datetime": dt_obj,
                }
            )

        timeline.sort(key=lambda item: item["datetime"])
        for item in timeline:
            item.pop("datetime", None)
        return timeline

    def detect_anomalies(self, metadata: dict[str, Any], timeline: list[dict[str, Any]]) -> list[str]:
        """Execute anomaly heuristics configured in the active ruleset."""
        anomalies: list[str] = []

        for anomaly_def in self.ruleset.anomalies:
            if not anomaly_def.enabled:
                continue

            # 1. Timestamp Inversion Check
            if anomaly_def.id in ("timestamp_inversion", "chronological_inversion"):
                tmpl = (
                    anomaly_def.template
                    or "Timestamp mismatch: '{curr_event}' occurs before '{prev_event}'."
                )
                mismatch_found = False

                # Check semantic creation vs modification timestamps
                created_events = []
                modified_events = []
                for event in timeline:
                    ev_name = event.get("event", "")
                    ev_l = ev_name.lower()
                    dt_obj = self._parse_datetime(event.get("timestamp"))
                    if not dt_obj:
                        continue
                    if any(t in ev_l for t in ["create", "capture"]):
                        created_events.append((ev_name, dt_obj))
                    elif any(t in ev_l for t in ["modif", "edit", "saved", "update"]):
                        modified_events.append((ev_name, dt_obj))

                for mod_name, mod_dt in modified_events:
                    for cre_name, cre_dt in created_events:
                        if mod_dt < cre_dt:
                            anomalies.append(tmpl.format(curr_event=mod_name, prev_event=cre_name))
                            mismatch_found = True
                            break
                    if mismatch_found:
                        break

                # Fallback check raw sequence if not already matched
                if not mismatch_found and len(timeline) >= 2:
                    parsed = []
                    for event in timeline:
                        dt_obj = self._parse_datetime(event.get("timestamp"))
                        if dt_obj:
                            parsed.append((event.get("event", ""), dt_obj))

                    for idx in range(1, len(parsed)):
                        prev_event, prev_dt = parsed[idx - 1]
                        curr_event, curr_dt = parsed[idx]
                        if curr_dt < prev_dt:
                            anomalies.append(tmpl.format(curr_event=curr_event, prev_event=prev_event))
                            break

            # 2. Multiple Editing Chains Check
            elif anomaly_def.id in ("multiple_editing_chains", "software_chains"):
                chain_sources = []
                for key, value in metadata.items():
                    key_l = str(key).lower()
                    if any(token in key_l for token in anomaly_def.software_keys):
                        val = str(value)
                        parts = re.split(r"[>;|,/]+", val)
                        for part in parts:
                            norm = part.strip()
                            if norm:
                                chain_sources.append(norm.lower())

                unique_chain = list(dict.fromkeys(chain_sources))
                if len(unique_chain) >= anomaly_def.min_distinct:
                    msg = anomaly_def.message or "Multiple editing chain detected from software metadata."
                    anomalies.append(msg)

            # 3. Stacked Metadata Blocks Check
            elif anomaly_def.id in ("stacked_metadata_blocks", "stacked_blocks"):
                block_count = 0
                for key in metadata.keys():
                    key_l = str(key).lower()
                    if any(token in key_l for token in anomaly_def.block_keys):
                        block_count += 1
                if block_count >= anomaly_def.min_count:
                    msg = anomaly_def.message or "Possible overwritten/stacked metadata blocks detected."
                    anomalies.append(msg)

        return anomalies

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------
    def _score_to_level(self, score: int) -> str:
        for start, end, label in self.ruleset.thresholds.to_levels_tuple():
            if start <= score <= end:
                return label
        return self.ruleset.thresholds.high_label

    def _has_key_containing(
        self,
        metadata: dict[str, Any],
        tokens: list[str],
        case_sensitive: bool = False,
    ) -> bool:
        for key, value in metadata.items():
            k_str = str(key) if case_sensitive else str(key).lower()
            v_str = str(value) if case_sensitive else str(value).lower()
            for tok in tokens:
                t_str = tok if case_sensitive else tok.lower()
                if t_str in k_str or t_str in v_str:
                    return True
        return False

    def _has_value_containing(
        self,
        metadata: dict[str, Any],
        tokens: list[str],
        case_sensitive: bool = False,
    ) -> bool:
        for value in metadata.values():
            v_str = str(value) if case_sensitive else str(value).lower()
            for tok in tokens:
                t_str = tok if case_sensitive else tok.lower()
                if t_str in v_str:
                    return True
        return False

    def _get_compiled_regex(self, pattern: str, case_sensitive: bool = False) -> Pattern[str]:
        cache_key = f"{'CS:' if case_sensitive else 'CI:'}{pattern}"
        if cache_key not in self._regex_cache:
            flags = 0 if case_sensitive else re.IGNORECASE
            self._regex_cache[cache_key] = re.compile(pattern, flags)
        return self._regex_cache[cache_key]

    def _extract_timestamp_candidates(self, metadata: dict[str, Any]) -> list[tuple[str, str, datetime]]:
        candidates: list[tuple[str, str, datetime]] = []
        key_hints = self.ruleset.timeline.candidate_keys

        for key, value in metadata.items():
            key_text = str(key)
            key_l = key_text.lower()
            if not any(h in key_l for h in key_hints):
                continue

            dt_obj = self._parse_datetime(value)
            if dt_obj is None:
                continue
            candidates.append((key_text, str(value), dt_obj))

        return candidates

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        text = str(value).strip()
        if not text:
            return None

        normalized = text.replace("Z", "+00:00").replace("/", "-")
        # Handle EXIF-like date: 2024:09:01 11:10:09
        if re.match(r"^\d{4}:\d{2}:\d{2}\s+\d{2}:\d{2}:\d{2}$", normalized):
            normalized = normalized.replace(":", "-", 2)

        # Try fromisoformat first
        try:
            return datetime.fromisoformat(normalized)
        except Exception:
            pass

        for fmt in self.ruleset.timeline.datetime_formats:
            try:
                return datetime.strptime(normalized, fmt)
            except Exception:
                continue

        return None

    def _create_fallback_ruleset(self) -> RuleSet:
        """In-memory fallback ruleset ensuring full operational capability even if YAML file is absent."""
        return RuleSet(
            version="1.0",
            name="TraceLens Fallback Ruleset",
            description="Built-in emergency fallback ruleset",
            thresholds=ThresholdConfig(
                low_min=0, low_max=29, low_label="LOW",
                medium_min=30, medium_max=64, medium_label="MEDIUM",
                high_min=65, high_max=100, high_label="HIGH",
            ),
            scoring={"max_score": 100, "anomaly_penalty": 20},
            timeline=TimelineConfig(),
            anomalies=[
                AnomalyRuleDefinition(
                    id="timestamp_inversion",
                    name="Timestamp Inversion",
                    template="Timestamp mismatch: '{curr_event}' occurs before '{prev_event}'.",
                    penalty=20,
                ),
                AnomalyRuleDefinition(
                    id="multiple_editing_chains",
                    name="Multiple Editing Chains",
                    software_keys=["software", "application", "producer", "editor"],
                    min_distinct=2,
                    message="Multiple editing chain detected from software metadata.",
                    penalty=15,
                ),
                AnomalyRuleDefinition(
                    id="stacked_metadata_blocks",
                    name="Stacked Metadata Blocks",
                    block_keys=["xmp", "iptc", "exif", "makernote", "thumbnail", "history"],
                    min_count=3,
                    message="Possible overwritten/stacked metadata blocks detected.",
                    penalty=15,
                ),
            ],
            rules=[
                RiskRuleDefinition(
                    id="gps_coordinates",
                    name="GPS Location Metadata",
                    category="geolocation",
                    score=30,
                    severity="HIGH",
                    reason="GPS or precise location metadata is present.",
                    remediation="Strip GPS/geotag coordinates before sharing to prevent physical location exposure.",
                    condition=RuleCondition(
                        any=[
                            RuleCondition(match_type="key_contains", keys=["gps", "latitude", "longitude", "lat", "lon", "location", "altitude"]),
                            RuleCondition(match_type="value_regex", pattern=r"[-+]?\d{1,3}\.\d+\s*,\s*[-+]?\d{1,3}\.\d+"),
                        ]
                    ),
                ),
                RiskRuleDefinition(
                    id="author_identity",
                    name="Author & User Identity",
                    category="identity",
                    score=18,
                    severity="MEDIUM",
                    reason="Author/user identity metadata is present.",
                    remediation="Remove creator, author, and user account metadata to protect personal identity.",
                    condition=RuleCondition(
                        match_type="key_contains",
                        keys=["author", "creator", "owner", "user", "last modified by", "artist", "by-line"],
                    ),
                ),
                RiskRuleDefinition(
                    id="device_information",
                    name="Device & Hardware Identifiers",
                    category="hardware",
                    score=18,
                    severity="MEDIUM",
                    reason="Device or camera-identifying information is present.",
                    remediation="Clear device serial numbers, camera model, and hardware identifiers.",
                    condition=RuleCondition(
                        match_type="key_contains",
                        keys=["device", "camera", "model", "serial", "imei", "make", "lens"],
                    ),
                ),
                RiskRuleDefinition(
                    id="editing_traces",
                    name="Editing Software & History",
                    category="software",
                    score=15,
                    severity="MEDIUM",
                    reason="Software/editor processing traces are present.",
                    remediation="Scrub editing software versions and revision history from document headers.",
                    condition=RuleCondition(
                        match_type="key_contains",
                        keys=["software", "application", "producer", "editor", "history", "tool", "source"],
                    ),
                ),
                RiskRuleDefinition(
                    id="hidden_blocks",
                    name="Embedded & Hidden Metadata Blocks",
                    category="forensic",
                    score=20,
                    severity="MEDIUM",
                    reason="Hidden/embedded metadata blocks (XMP/EXIF/IPTC/MakerNote) detected.",
                    remediation="Consider sanitizing all embedded metadata blocks prior to public distribution.",
                    condition=RuleCondition(
                        match_type="key_contains",
                        keys=["xmp", "iptc", "exif", "makernote", "thumbnail", "private tag", "icc profile"],
                    ),
                ),
                RiskRuleDefinition(
                    id="network_traces",
                    name="Network & URL Traces",
                    category="privacy",
                    score=15,
                    severity="MEDIUM",
                    reason="Internal URLs, UNC network paths, or IP addresses discovered in metadata.",
                    remediation="Remove sensitive intranet URLs, hostnames, and IP paths.",
                    condition=RuleCondition(
                        any=[
                            RuleCondition(match_type="value_regex", pattern=r"https?://|\\\\[a-zA-Z0-9_.-]+\\"),
                            RuleCondition(match_type="key_contains", keys=["uri", "url", "server", "host", "domain", "ip address"]),
                        ]
                    ),
                ),
                RiskRuleDefinition(
                    id="cryptographic_signatures",
                    name="Digital Signatures & Certificates",
                    category="security",
                    score=10,
                    severity="LOW",
                    reason="Digital certificates or cryptographic signature blocks present.",
                    remediation="Verify if digital signature exposes signer identity or internal enterprise PKI.",
                    condition=RuleCondition(
                        match_type="key_contains",
                        keys=["signature", "certificate", "cert", "signer", "fingerprint"],
                    ),
                ),
            ],
        )


YamlRiskEngine = RiskEngine
