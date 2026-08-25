"""Editor service orchestrating metadata modification, validation, sanitization, and file writing."""

from __future__ import annotations

import os
import shutil
from typing import Any

from src.config.logging_config import get_logger
from src.core.database import db as db_module
from src.core.editor import editor as editor_module

logger = get_logger("core.services.editor")


class MetadataEditorService:
    """Application service for editing, sanitizing, and writing metadata to files and database."""

    def __init__(
        self,
        editor: editor_module.MetadataEditor | None = None,
        database: db_module.MetadataDatabase | None = None,
    ) -> None:
        self.database = database or db_module.db_manager
        self.editor = editor or editor_module.MetadataEditor(db_client=self.database)


    def parse_editor_text(self, text: str) -> dict[str, Any]:
        """Parse plain-text metadata from the editor into structured headers and metadata dicts."""
        return self.editor.parse_editor_text(text)

    def validate_metadata(self, parsed_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate parsed metadata dictionary for required fields and content."""
        return self.editor.validate_metadata(parsed_data)

    def can_write_metadata(self, file_path: str) -> bool:
        """Check whether direct file writing is supported for this file extension."""
        return self.editor.can_write_metadata(file_path)

    def save_to_database(self, file_path: str, parsed_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate and persist updated metadata to the database record.

        Args:
            file_path: Path to the target file.
            parsed_data: Parsed metadata containing 'headers' and 'metadata'.

        Returns:
            tuple: (success, message)
        """
        return self.editor.save_edited_metadata(file_path, parsed_data)

    def write_to_file(
        self,
        file_path: str,
        parsed_data: dict[str, Any],
        backup: bool = False,
    ) -> tuple[bool, str]:
        """Write modified metadata directly into the physical file (PDF, PNG, JPEG, MP3, text).

        Args:
            file_path: Path to the physical file.
            parsed_data: Parsed metadata containing 'metadata' dictionary.
            backup: Whether to create a backup file (.bak) before writing.

        Returns:
            tuple: (success, message)
        """
        if not os.path.exists(file_path):
            return False, f"File does not exist: {file_path}"

        if not self.can_write_metadata(file_path):
            ext = os.path.splitext(file_path)[1]
            return False, f"Writing metadata to '{ext}' files is not currently supported."

        if backup:
            backup_path = f"{file_path}.bak"
            try:
                shutil.copy2(file_path, backup_path)
            except Exception as e:
                return False, f"Failed to create backup copy: {e}"

        metadata = parsed_data.get("metadata", parsed_data)
        return self.editor.write_metadata_to_file(file_path, metadata)

    def strip_sensitive_metadata(
        self,
        file_path: str,
        backup: bool = True,
    ) -> tuple[bool, str]:
        """Sanitize a file by stripping GPS, Author, Camera, and other sensitive metadata tags.

        Args:
            file_path: Path to the file.
            backup: Whether to create a .bak backup file.

        Returns:
            tuple: (success, message)
        """
        if not os.path.exists(file_path):
            return False, f"File does not exist: {file_path}"

        if not self.can_write_metadata(file_path):
            ext = os.path.splitext(file_path)[1]
            return False, f"Sanitizing '{ext}' files is not currently supported."

        if backup:
            backup_path = f"{file_path}.bak"
            try:
                shutil.copy2(file_path, backup_path)
            except Exception as e:
                return False, f"Failed to create backup copy: {e}"

        # Clean sanitized metadata dictionary
        sanitized_metadata: dict[str, Any] = {}
        return self.editor.write_metadata_to_file(file_path, sanitized_metadata)

    def get_editable_text(self, db_record: tuple[Any, ...] | dict[str, Any]) -> str:
        """Format a database record or metadata dict into editable multi-line text."""
        return self.editor.get_editable_text(db_record)
