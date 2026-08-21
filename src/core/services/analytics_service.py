"""Analytics and metrics service calculating aggregate metadata intelligence and dashboard statistics."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from src.core.database import db as db_module
from src.core.risk import risk_analyzer as risk_module
from src.models.analytics import AnalyticsSummary


class AnalyticsService:
    """Application service for computing statistical analytics and dashboard metrics."""

    def __init__(
        self,
        database: db_module.MetadataDatabase | None = None,
        analyzer: risk_module.PrivacyForensicAnalyzer | None = None,
    ) -> None:
        self.database = database or db_module.db_manager
        self.analyzer = analyzer or risk_module.analyzer

    @staticmethod
    def parse_size_to_bytes(size_str: str | int | float | None) -> int:
        """Convert a human-readable size string (e.g. '1.5 MB') or integer to bytes."""
        if size_str is None:
            return 0
        if isinstance(size_str, (int, float)):
            return int(size_str)

        text = str(size_str).strip().upper()
        if not text or text in ("UNKNOWN", "NONE", "N/A"):
            return 0

        # Try parsing plain numeric string
        try:
            return int(text)
        except ValueError:
            pass

        units = {
            "TB": 1024**4,
            "GB": 1024**3,
            "MB": 1024**2,
            "KB": 1024,
            "B": 1,
        }

        for unit, multiplier in units.items():
            if text.endswith(unit):
                num_part = text[:-len(unit)].strip()
                try:
                    return int(float(num_part) * multiplier)
                except ValueError:
                    return 0

        return 0

    @staticmethod
    def format_size(size_bytes: int | float | None) -> str:
        """Convert byte count to a human-readable string (e.g. '2.34 MB')."""
        if size_bytes is None:
            return "0.0 B"
        try:
            val = float(size_bytes)
        except (ValueError, TypeError):
            return "0.0 B"

        if val <= 0:
            return "0.0 B"

        units = ["B", "KB", "MB", "GB", "TB"]
        idx = 0
        while val >= 1024.0 and idx < len(units) - 1:
            val /= 1024.0
            idx += 1

        if idx == 0:
            return f"{int(val)} {units[idx]}"
        return f"{val:.1f} {units[idx]}"

    def filter_records(
        self,
        records: list[tuple[Any, ...]],
        date_range: str = "all",
        file_type: str = "all",
        search_query: str = "",
    ) -> list[tuple[Any, ...]]:
        """Filter a list of raw database tuples by date range, file type, and search keyword."""
        filtered = list(records)
        now = datetime.now()

        # Date range filtering
        if date_range == "today":
            filtered = [r for r in filtered if len(r) > 5 and str(r[5]).startswith(now.strftime("%Y-%m-%d"))]
        elif date_range == "week":
            cutoff = now - timedelta(days=7)
            filtered = [r for r in filtered if len(r) > 5 and self._parse_iso_date(r[5]) >= cutoff]
        elif date_range == "month":
            cutoff = now - timedelta(days=30)
            filtered = [r for r in filtered if len(r) > 5 and self._parse_iso_date(r[5]) >= cutoff]
        elif date_range == "year":
            cutoff = now - timedelta(days=365)
            filtered = [r for r in filtered if len(r) > 5 and self._parse_iso_date(r[5]) >= cutoff]

        # File type filtering
        if file_type and file_type.lower() != "all":
            ft_clean = file_type.lower().lstrip(".")
            filtered = [r for r in filtered if len(r) > 4 and str(r[4]).lower().lstrip(".") == ft_clean]

        # Search query filtering
        if search_query:
            q = search_query.lower()
            filtered = [
                r for r in filtered
                if (len(r) > 1 and q in str(r[1]).lower())
                or (len(r) > 2 and q in str(r[2]).lower())
                or (len(r) > 7 and q in str(r[7]).lower())
            ]

        return filtered

    def calculate_enhanced_stats(self, records: list[tuple[Any, ...]]) -> dict[str, Any]:
        """Compute rich statistics dictionary from records."""
        total_files = len(records)
        if total_files == 0:
            return {
                "total_files": 0,
                "total_size_bytes": 0,
                "total_size_formatted": "0.0 B",
                "avg_size_bytes": 0,
                "avg_size_formatted": "0.0 B",
                "file_type_counts": {},
                "risk_distribution": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
                "avg_risk_score": 0.0,
                "top_threats": [],
                "recent_activity": [],
            }

        total_bytes = 0
        type_counts: Counter[str] = Counter()
        risk_dist = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        total_risk_score = 0
        threat_counter: Counter[str] = Counter()
        recent_activity: list[dict[str, Any]] = []

        for row in records:
            # Tuple: (id, file_path, file_name, size, type, extracted_at, modified_on, full_metadata)
            size_formatted = row[3] if len(row) > 3 else "0 B"
            b_size = self.parse_size_to_bytes(size_formatted)
            total_bytes += b_size

            ftype = (str(row[4]).upper().lstrip(".") if len(row) > 4 and row[4] else "UNKNOWN")
            type_counts[ftype] += 1

            # Metadata parsing for risk analysis
            raw_meta = row[7] if len(row) > 7 else "{}"
            if isinstance(raw_meta, str):
                try:
                    meta_dict = json.loads(raw_meta)
                except Exception:
                    meta_dict = {}
            elif isinstance(raw_meta, dict):
                meta_dict = raw_meta
            else:
                meta_dict = {}

            analysis = self.analyzer.analyze_file(
                meta_dict,
                file_path=row[1] if len(row) > 1 else "",
                fallback_timestamps={"Extracted At": row[5] if len(row) > 5 else "", "Modified On": row[6] if len(row) > 6 else ""},
            )

            score = analysis.get("risk_score", 0)
            level = analysis.get("risk_level", "LOW")
            total_risk_score += score
            risk_dist[level] = risk_dist.get(level, 0) + 1

            for reason in analysis.get("reasons", []):
                if reason and "no high-sensitivity" not in reason.lower():
                    threat_counter[reason] += 1

            if len(recent_activity) < 10:
                recent_activity.append({
                    "id": row[0] if len(row) > 0 else 0,
                    "file_name": row[2] if len(row) > 2 else "",
                    "file_size": size_formatted,
                    "extracted_at": row[5] if len(row) > 5 else "",
                    "risk_level": level,
                    "risk_score": score,
                })

        avg_bytes = int(total_bytes / total_files) if total_files > 0 else 0
        avg_risk = float(total_risk_score / total_files) if total_files > 0 else 0.0

        top_threats = [{"reason": k, "count": v} for k, v in threat_counter.most_common(5)]

        return {
            "total_files": total_files,
            "total_size_bytes": total_bytes,
            "total_size_formatted": self.format_size(total_bytes),
            "avg_size_bytes": avg_bytes,
            "avg_size_formatted": self.format_size(avg_bytes),
            "file_type_counts": dict(type_counts),
            "risk_distribution": risk_dist,
            "avg_risk_score": round(avg_risk, 1),
            "top_threats": top_threats,
            "recent_activity": recent_activity,
        }

    def get_dashboard_metrics(
        self,
        records: list[tuple[Any, ...]] | None = None,
        date_range: str = "all",
        file_type: str = "all",
        search_query: str = "",
    ) -> AnalyticsSummary:
        """Get an AnalyticsSummary domain model based on database records."""
        if records is None:
            records = self.database.fetch_all_metadata()

        filtered = self.filter_records(
            records=records,
            date_range=date_range,
            file_type=file_type,
            search_query=search_query,
        )

        stats = self.calculate_enhanced_stats(filtered)

        return AnalyticsSummary(
            total_files=stats["total_files"],
            total_size_bytes=stats["total_size_bytes"],
            total_size_formatted=stats["total_size_formatted"],
            avg_size_formatted=stats["avg_size_formatted"],
            file_type_counts=stats["file_type_counts"],
            risk_distribution=stats["risk_distribution"],
            avg_risk_score=stats["avg_risk_score"],
            top_threats=stats["top_threats"],
            recent_activity=stats["recent_activity"],
        )

    def _parse_iso_date(self, date_str: Any) -> datetime:
        """Helper to parse varied date formats safely."""
        if not date_str:
            return datetime.min
        text = str(date_str).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return datetime.min
