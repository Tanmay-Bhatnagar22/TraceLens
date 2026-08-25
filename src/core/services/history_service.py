"""History and database service managing metadata records, search, filtering, and persistence."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from src.config.logging_config import get_logger
from src.core.database import db as db_module
from src.models.metadata import MetadataRecord

logger = get_logger("core.services.history")


class HistoryService:
    """Application service for historical metadata retrieval, querying, filtering, and DB maintenance."""

    def __init__(
        self,
        database: db_module.MetadataDatabase | None = None,
    ) -> None:
        self.database = database or db_module.db_manager


    def get_record_by_id(self, record_id: int) -> MetadataRecord | None:
        """Fetch a single record by its primary key ID."""
        row = self.database.fetch_metadata_by_id(record_id)
        if not row:
            return None
        return MetadataRecord.from_row(row)

    def get_latest_by_path(self, file_path: str) -> MetadataRecord | None:
        """Fetch the most recent metadata record matching the exact file path."""
        row = self.database.fetch_latest_by_path(file_path)
        if not row:
            return None
        return MetadataRecord.from_row(row)

    def get_all_records(self) -> list[MetadataRecord]:
        """Fetch all stored metadata records as domain models."""
        rows = self.database.fetch_all_metadata()
        return [MetadataRecord.from_row(row) for row in rows]

    def get_all_raw_records(self) -> list[tuple[Any, ...]]:
        """Fetch raw tuples for performance-critical views or treeviews."""
        return self.database.fetch_all_metadata()

    def filter_records(
        self,
        search_query: str = "",
        file_type: str = "",
        date_filter: str = "",
        sort_by: str = "id",
        ascending: bool = False,
    ) -> list[MetadataRecord]:
        """Filter, search, and sort records based on criteria.

        Args:
            search_query: Substring to match across file path, name, or metadata content.
            file_type: Specific file extension or category to filter by.
            date_filter: Date constraint ('Today', 'Last 7 Days', 'Last 30 Days', 'Last Year', or YYYY-MM-DD).
            sort_by: Column to sort by ('id', 'file_name', 'file_size_formatted', 'extracted_at', 'modified_on').
            ascending: Sort direction.

        Returns:
            List of filtered MetadataRecord domain models.
        """
        rows = self.database.filter_and_search_data(
            search_query=search_query,
            file_type=file_type,
            date_filter=date_filter,
            sort_by=sort_by,
            ascending=ascending,
        )
        return [MetadataRecord.from_row(row) for row in rows]

    def delete_record(self, record_id: int) -> bool:
        """Delete a single metadata record by its ID."""
        try:
            self.database.delete_record(record_id)
            return True
        except Exception:
            return False

    def clear_history(self) -> bool:
        """Delete all metadata records from the database."""
        try:
            self.database.clear_metadata()
            return True
        except Exception:
            return False

    def get_database_stats(self) -> dict[str, Any]:
        """Get aggregate database statistics (total records, file types, sizes, etc.)."""
        return self.database.get_database_stats()

    def optimize_database(self) -> tuple[bool, str]:
        """Perform SQLite database optimization (VACUUM, ANALYZE, integrity check)."""
        return self.database.optimize_database()

    def export_history(self, file_format: str, output_path: str | None = None) -> tuple[bool, str]:
        """Export all database records to a file (JSON, XML, CSV, Excel).

        Args:
            file_format: Desired export format ('json', 'xml', 'csv', 'excel').
            output_path: Target destination path.

        Returns:
            tuple: (success, message_or_path)
        """
        return self.database.export_data(file_format, output_path)
