import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


@dataclass
class RiskRule:
    name: str
    score: int
    reason: str
    checker: Callable[[dict[str, Any]], bool]


class PrivacyForensicAnalyzer:
    """Combined privacy risk scanner + forensic timeline generator.

    Designed to be modular: add new rules by appending to ``self.rules``.
    """

    RISK_LEVELS = (
        (0, 29, "LOW"),
        (30, 64, "MEDIUM"),
        (65, 100, "HIGH"),
    )

    def __init__(self) -> None:
        self.rules: list[RiskRule] = [
            RiskRule(
                name="gps_coordinates",
                score=30,
                reason="GPS or precise location metadata is present.",
                checker=self._has_gps_coordinates,
            ),
            RiskRule(
                name="author_identity",
                score=18,
                reason="Author/user identity metadata is present.",
                checker=lambda m: self._has_any_key(m, ["author", "creator", "owner", "user", "last modified by"]),
            ),
            RiskRule(
                name="device_information",
                score=18,
                reason="Device or camera-identifying information is present.",
                checker=lambda m: self._has_any_key(m, ["device", "camera", "model", "serial", "imei", "make"]),
            ),
            RiskRule(
                name="editing_traces",
                score=15,
                reason="Software/editor processing traces are present.",
                checker=lambda m: self._has_any_key(m, ["software", "application", "producer", "editor", "history", "tool"]),
            ),
            RiskRule(
                name="hidden_blocks",
                score=20,
                reason="Hidden/embedded metadata blocks (XMP/EXIF/IPTC/MakerNote) detected.",
                checker=lambda m: self._has_any_key(m, ["xmp", "iptc", "exif", "makernote", "thumbnail", "private tag"]),
            ),
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze_file(
        self,
        metadata: dict[str, Any] | None,
        file_path: str | None = None,
        fallback_timestamps: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = metadata if isinstance(metadata, dict) else {}
        matched_rules = []
        score = 0

        for rule in self.rules:
            try:
                if rule.checker(metadata):
                    matched_rules.append(rule)
                    score += rule.score
            except Exception:
                continue

        timeline = self.build_timeline(metadata, fallback_timestamps=fallback_timestamps)
        anomalies = self.detect_anomalies(metadata, timeline)

        if anomalies:
            score += 20

        score = min(score, 100)
        level = self._score_to_level(score)

        reasons = [rule.reason for rule in matched_rules]
        reasons.extend(anomalies)
        if not reasons:
            reasons = ["No high-sensitivity metadata indicators were detected."]

        return {
            "file_path": file_path or "",
            "file_name": os.path.basename(file_path) if file_path else "",
            "risk_score": score,
            "risk_level": level,
            "reasons": reasons,
            "matched_rules": [rule.name for rule in matched_rules],
            "timeline": timeline,
            "anomalies": anomalies,
            "event_count": len(timeline),
        }

    def analyze_batch(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze a list of file entries and build folder-level summary.

        Each entry expects keys: ``file_path`` and ``metadata``.
        """
        results = []
        risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
        folder_stats: dict[str, dict[str, int]] = {}

        for entry in entries:
            file_path = entry.get("file_path", "")
            metadata = entry.get("metadata", {})
            item = self.analyze_file(metadata, file_path)
            results.append(item)
            risk_counts[item["risk_level"]] = risk_counts.get(item["risk_level"], 0) + 1

            folder = os.path.dirname(file_path) if file_path else "Unknown"
            if folder not in folder_stats:
                folder_stats[folder] = {"total": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0}
            folder_stats[folder]["total"] += 1
            folder_stats[folder][item["risk_level"]] += 1

        highest = max(results, key=lambda x: x["risk_score"], default=None)
        return {
            "total_files": len(results),
            "risk_counts": risk_counts,
            "folders": folder_stats,
            "highest_risk": highest,
            "results": results,
        }

    def build_timeline(self, metadata: dict[str, Any], fallback_timestamps: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        candidates = self._extract_timestamp_candidates(metadata)

        # Fallback timeline source when metadata has no useful timeline keys
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
        anomalies = []

        if len(timeline) >= 2:
            parsed = []
            for event in timeline:
                dt_obj = self._parse_datetime(event.get("timestamp"))
                if dt_obj:
                    parsed.append((event.get("event", ""), dt_obj))

            for idx in range(1, len(parsed)):
                prev_event, prev_dt = parsed[idx - 1]
                curr_event, curr_dt = parsed[idx]
                if curr_dt < prev_dt:
                    anomalies.append(f"Timestamp mismatch: '{curr_event}' occurs before '{prev_event}'.")
                    break

        chain_sources = []
        for key, value in metadata.items():
            key_l = str(key).lower()
            if any(token in key_l for token in ["software", "application", "producer", "editor"]):
                val = str(value)
                parts = re.split(r"[>;|,/]+", val)
                for part in parts:
                    norm = part.strip()
                    if norm:
                        chain_sources.append(norm.lower())

        unique_chain = list(dict.fromkeys(chain_sources))
        if len(unique_chain) >= 2:
            anomalies.append("Multiple editing chain detected from software metadata.")

        block_count = 0
        for key in metadata.keys():
            key_l = str(key).lower()
            if any(token in key_l for token in ["xmp", "iptc", "exif", "makernote", "thumbnail", "history"]):
                block_count += 1
        if block_count >= 3:
            anomalies.append("Possible overwritten/stacked metadata blocks detected.")

        return anomalies

    # ------------------------------------------------------------------
    # Rule helpers
    # ------------------------------------------------------------------
    def _score_to_level(self, score: int) -> str:
        for start, end, label in self.RISK_LEVELS:
            if start <= score <= end:
                return label
        return "HIGH"

    def _has_any_key(self, metadata: dict[str, Any], keywords: list[str]) -> bool:
        for key, value in metadata.items():
            key_l = str(key).lower()
            val_l = str(value).lower()
            for kw in keywords:
                if kw in key_l or kw in val_l:
                    return True
        return False

    def _has_gps_coordinates(self, metadata: dict[str, Any]) -> bool:
        gps_keys = ["gps", "latitude", "longitude", "lat", "lon", "location"]
        if self._has_any_key(metadata, gps_keys):
            return True

        # Raw coordinate pattern
        coord_pattern = re.compile(r"[-+]?\d{1,3}\.\d+\s*,\s*[-+]?\d{1,3}\.\d+")
        for value in metadata.values():
            if coord_pattern.search(str(value)):
                return True
        return False

    def _extract_timestamp_candidates(self, metadata: dict[str, Any]) -> list[tuple[str, str, datetime]]:
        candidates = []
        key_hints = [
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

        formats = [
            None,  # try fromisoformat first
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%Y-%m-%d",
            "%d-%m-%Y",
        ]

        for fmt in formats:
            try:
                if fmt is None:
                    return datetime.fromisoformat(normalized)
                return datetime.strptime(normalized, fmt)
            except Exception:
                continue

        return None


_analyzer = PrivacyForensicAnalyzer()


def analyze_metadata(
    metadata: dict[str, Any] | None,
    file_path: str | None = None,
    fallback_timestamps: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _analyzer.analyze_file(metadata, file_path, fallback_timestamps=fallback_timestamps)


def analyze_batch(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return _analyzer.analyze_batch(entries)
