"""Domain models for metadata records and extraction results."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MetadataRecord:
    """Represents a persisted metadata record in the database."""

    id: int
    file_path: str
    file_name: str
    file_size_formatted: str = "0 B"
    file_type: str = "unknown"
    extracted_at: str = ""
    modified_on: str = ""
    full_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> MetadataRecord:
        """Create a MetadataRecord instance from a database row tuple."""
        raw_meta = row[7] if len(row) > 7 else "{}"
        if isinstance(raw_meta, str):
            try:
                meta_dict = json.loads(raw_meta)
            except Exception:
                meta_dict = {"raw": raw_meta}
        elif isinstance(raw_meta, dict):
            meta_dict = raw_meta
        else:
            meta_dict = {}

        return cls(
            id=row[0] if len(row) > 0 else 0,
            file_path=row[1] if len(row) > 1 else "",
            file_name=row[2] if len(row) > 2 else "",
            file_size_formatted=row[3] if len(row) > 3 else "0 B",
            file_type=row[4] if len(row) > 4 else "unknown",
            extracted_at=row[5] if len(row) > 5 else "",
            modified_on=row[6] if len(row) > 6 else "",
            full_metadata=meta_dict,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the record to a dictionary."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_size_formatted": self.file_size_formatted,
            "file_type": self.file_type,
            "extracted_at": self.extracted_at,
            "modified_on": self.modified_on,
            "full_metadata": self.full_metadata,
        }


@dataclass
class ExtractionResult:
    """Represents the outcome of extracting metadata from a single file."""

    file_path: str
    success: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    db_record_id: int | None = None
    error: str | None = None
    file_name: str = ""
    file_size_formatted: str = "0 B"
    file_type: str = "unknown"
    modified_on: str = ""
    extracted_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert extraction result to a dictionary."""
        return {
            "file_path": self.file_path,
            "success": self.success,
            "metadata": self.metadata,
            "db_record_id": self.db_record_id,
            "error": self.error,
            "file_name": self.file_name,
            "file_size_formatted": self.file_size_formatted,
            "file_type": self.file_type,
            "modified_on": self.modified_on,
            "extracted_at": self.extracted_at,
        }


@dataclass
class BatchExtractionResult:
    """Represents the outcome of extracting metadata from multiple files."""

    total: int = 0
    successful: int = 0
    failed: int = 0
    items: list[ExtractionResult] = field(default_factory=list)
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: str = ""
    duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate the percentage of successful extractions."""
        if self.total == 0:
            return 0.0
        return (self.successful / self.total) * 100.0

    def to_dict(self) -> dict[str, Any]:
        """Convert batch extraction result to a dictionary."""
        return {
            "total": self.total,
            "successful": self.successful,
            "failed": self.failed,
            "success_rate": round(self.success_rate, 2),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": round(self.duration_seconds, 3),
            "items": [item.to_dict() for item in self.items],
        }
