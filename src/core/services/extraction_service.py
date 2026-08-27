"""Extraction service orchestrating file validation, metadata extraction, and storage."""

from __future__ import annotations

import mimetypes
import os
import time
from datetime import datetime
from typing import Any, Callable, Iterable

from src.config.logging_config import get_logger
from src.core.database import db as db_module
from src.core.extractor import extractor as extractor_module
from src.models.metadata import BatchExtractionResult, ExtractionResult

logger = get_logger("core.services.extraction")


class ExtractionService:
    """Application service for extracting and managing file metadata."""

    SUPPORTED_EXTENSIONS = {
        # Documents
        ".pdf", ".docx", ".doc", ".xlsx", ".xlsm", ".xltx", ".xls", ".pptx", ".ppt", ".odt", ".ods", ".odp", ".txt", ".rtf",
        # Images & Vector
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".ico", ".svg",
        # Audio
        ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif",
        # Video & Containers
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".3gp", ".mpg", ".mpeg",
        # Archives
        ".zip", ".tar", ".gz", ".tgz", ".bz2", ".tbz2", ".xz", ".txz", ".7z",
        # Structured Data & Config
        ".json", ".csv", ".tsv", ".xml", ".html", ".htm", ".xhtml", ".yaml", ".yml",
        ".ini", ".cfg", ".conf", ".toml", ".env", ".sql",
        # Source Code & Scripts
        ".py", ".pyw", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
        ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".cs",
        ".java", ".go", ".rs", ".php", ".rb", ".swift", ".kt", ".kts",
        ".sh", ".bash", ".zsh", ".bat", ".cmd", ".ps1", ".lua", ".r",
        ".scala", ".dart", ".md", ".markdown", ".css", ".scss", ".less",
        # Databases
        ".db", ".sqlite", ".sqlite3", ".db3", ".s3db", ".sl3",
    }

    def __init__(
        self,
        extractor: extractor_module.MetadataExtractor | None = None,
        database: db_module.MetadataDatabase | None = None,
    ) -> None:
        self.database = database or db_module.db_manager
        self.extractor = extractor or extractor_module.MetadataExtractor(db_client=self.database)


    def validate_file(self, file_path: str) -> tuple[bool, str]:
        """Validate that a target path exists and is a readable file."""
        if not file_path:
            return False, "No file path provided."
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        if not os.path.isfile(file_path):
            return False, f"Path is not a regular file: {file_path}"
        return True, ""

    def get_file_info(self, file_path: str) -> dict[str, Any]:
        """Get basic file metadata like name, formatted size, type, and modified time."""
        is_valid, _ = self.validate_file(file_path)
        if not is_valid:
            return {
                "file_name": os.path.basename(file_path) if file_path else "",
                "file_size_formatted": "0 B",
                "file_type": "unknown",
                "modified_on": "",
            }

        file_name = os.path.basename(file_path)
        _, ext = os.path.splitext(file_name)
        file_type = (ext[1:].lower() if ext.startswith(".") else ext.lower()) or "unknown"

        try:
            stat = os.stat(file_path)
            size_bytes = stat.st_size
            modified_on = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            formatted_size = self.database.format_file_size(size_bytes)
        except Exception:
            formatted_size = "0 B"
            modified_on = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return {
            "file_name": file_name,
            "file_size_formatted": formatted_size,
            "file_type": file_type,
            "modified_on": modified_on,
        }

    def extract_file(
        self,
        file_path: str,
        persist: bool = True,
    ) -> ExtractionResult:
        """Extract metadata from a single file with optional persistence.

        Args:
            file_path: Path to the target file.
            persist: Whether to store the extracted record in the database.

        Returns:
            ExtractionResult domain model.
        """
        is_valid, error_msg = self.validate_file(file_path)
        info = self.get_file_info(file_path)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not is_valid:
            return ExtractionResult(
                file_path=file_path,
                success=False,
                error=error_msg,
                file_name=info["file_name"],
                file_size_formatted=info["file_size_formatted"],
                file_type=info["file_type"],
                modified_on=info["modified_on"],
                extracted_at=now_str,
            )

        try:
            raw_meta = self.extractor.extract(file_path)
            if not raw_meta or not isinstance(raw_meta, dict):
                return ExtractionResult(
                    file_path=file_path,
                    success=False,
                    error="Extraction returned no metadata.",
                    file_name=info["file_name"],
                    file_size_formatted=info["file_size_formatted"],
                    file_type=info["file_type"],
                    modified_on=info["modified_on"],
                    extracted_at=now_str,
                )

            if "Error" in raw_meta:
                return ExtractionResult(
                    file_path=file_path,
                    success=False,
                    error=raw_meta["Error"],
                    metadata=raw_meta,
                    file_name=info["file_name"],
                    file_size_formatted=info["file_size_formatted"],
                    file_type=info["file_type"],
                    modified_on=info["modified_on"],
                    extracted_at=now_str,
                )

            db_id = None
            if persist:
                try:
                    row = self.database.insert_metadata(file_path, raw_meta)
                    if row and len(row) > 0:
                        db_id = row[0]
                except Exception as exc:
                    return ExtractionResult(
                        file_path=file_path,
                        success=False,
                        error=f"Failed to persist metadata: {exc}",
                        metadata=raw_meta,
                        file_name=info["file_name"],
                        file_size_formatted=info["file_size_formatted"],
                        file_type=info["file_type"],
                        modified_on=info["modified_on"],
                        extracted_at=now_str,
                    )

            return ExtractionResult(
                file_path=file_path,
                success=True,
                metadata=raw_meta,
                db_record_id=db_id,
                file_name=info["file_name"],
                file_size_formatted=info["file_size_formatted"],
                file_type=info["file_type"],
                modified_on=info["modified_on"],
                extracted_at=now_str,
            )

        except Exception as e:
            return ExtractionResult(
                file_path=file_path,
                success=False,
                error=f"Unexpected extraction failure: {e}",
                file_name=info["file_name"],
                file_size_formatted=info["file_size_formatted"],
                file_type=info["file_type"],
                modified_on=info["modified_on"],
                extracted_at=now_str,
            )

    def extract_batch(
        self,
        file_paths: Iterable[str],
        persist: bool = True,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> BatchExtractionResult:
        """Extract metadata from multiple files with progress reporting.

        Args:
            file_paths: Collection of file paths to process.
            persist: Whether to store each record in the database.
            progress_callback: Optional callable(status_msg, percentage).

        Returns:
            BatchExtractionResult domain model.
        """
        paths_list = list(file_paths)
        total = len(paths_list)
        start_time = time.time()
        start_iso = datetime.now().isoformat()

        items: list[ExtractionResult] = []
        successful = 0
        failed = 0

        for i, path in enumerate(paths_list):
            if progress_callback:
                pct = (i / total) * 100.0 if total else 0.0
                try:
                    progress_callback(f"Processing ({i + 1}/{total}): {os.path.basename(path)}", pct)
                except Exception:
                    pass

            result = self.extract_file(path, persist=persist)
            items.append(result)
            if result.success:
                successful += 1
            else:
                failed += 1

        if progress_callback:
            try:
                progress_callback("Batch extraction complete.", 100.0)
            except Exception:
                pass

        end_time = time.time()
        end_iso = datetime.now().isoformat()

        return BatchExtractionResult(
            total=total,
            successful=successful,
            failed=failed,
            items=items,
            start_time=start_iso,
            end_time=end_iso,
            duration_seconds=end_time - start_time,
        )

    def extract_directory(
        self,
        directory_path: str,
        recursive: bool = True,
        extensions: list[str] | None = None,
        persist: bool = True,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> BatchExtractionResult:
        """Scan a directory and extract metadata from all matching files."""
        if not os.path.exists(directory_path) or not os.path.isdir(directory_path):
            return BatchExtractionResult(
                total=0,
                successful=0,
                failed=0,
                items=[],
                end_time=datetime.now().isoformat(),
            )

        allowed_exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions} if extensions else None

        collected_paths: list[str] = []
        if recursive:
            for root, _, files in os.walk(directory_path):
                for f in sorted(files):
                    ext = os.path.splitext(f)[1].lower()
                    if allowed_exts is None or ext in allowed_exts:
                        collected_paths.append(os.path.join(root, f))
        else:
            for f in sorted(os.listdir(directory_path)):
                full_p = os.path.join(directory_path, f)
                if os.path.isfile(full_p):
                    ext = os.path.splitext(f)[1].lower()
                    if allowed_exts is None or ext in allowed_exts:
                        collected_paths.append(full_p)

        return self.extract_batch(collected_paths, persist=persist, progress_callback=progress_callback)
