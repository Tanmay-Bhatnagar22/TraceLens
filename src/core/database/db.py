import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import json
import os
import tempfile
import report


def _default_db_path() -> str:
    """Return a writable default SQLite path for the current user.

    Installed apps can run from read-only locations (for example Program Files),
    so the database must live under a user-writable data directory.
    """
    env_override = os.getenv("TRACELENS_DB_PATH")
    if env_override:
        return env_override

    if os.name == "nt":
        base_dir = os.getenv("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base_dir = os.getenv("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")

    app_dir = os.path.join(base_dir, "TraceLens")
    try:
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, "file_metadata.db")
    except Exception:
        # Last-resort fallback prevents startup failure on unexpected FS issues.
        return os.path.join(tempfile.gettempdir(), "TraceLens-file_metadata.db")


class MetadataDatabase:
    """Object-oriented wrapper around SQLite metadata storage."""

    def __init__(self, db_path: str | None = None, reporter=report) -> None:
        self.db_path = db_path or _default_db_path()
        self.reporter = reporter
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._ensure_tables()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _connect(self):
        """Open a connection to the SQLite database.
        
        Returns:
            sqlite3.Connection: Database connection object.
        """
        return sqlite3.connect(self.db_path)

    def _ensure_tables(self) -> None:
        """Create the metadata table if it doesn't already exist.
        
        Table schema:
            - id: Auto-incrementing primary key
            - file_path: Path to the source file
            - file_name: Extracted filename
            - file_size_formatted: Human-readable file size
            - file_type: File extension
            - extracted_at: Timestamp of extraction
            - modified_on: Last modification time of the source file
            - full_metadata: JSON string of complete metadata
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size_formatted TEXT,
                    file_type TEXT,
                    extracted_at TEXT NOT NULL,
                    modified_on TEXT,
                    full_metadata TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @staticmethod
    def format_file_size(size_bytes):
        """Convert file size in bytes to human-readable format.
        
        Args:
            size_bytes (int): Size of the file in bytes.
            
        Returns:
            str: Human-readable file size (e.g., '1.50 MB', '0 B').
        """
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {size_names[i]}"

    def insert_metadata(self, file_path, metadata):
        """Insert metadata record for a file into the database.
        
        Args:
            file_path (str): Path to the file to extract metadata from.
            metadata (dict): Dictionary containing the extracted metadata.
            
        Returns:
            tuple: Database row for the newly inserted record.
        """
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else None
        file_size_formatted = self.format_file_size(file_size) if file_size else "Unknown"
        file_type = os.path.splitext(file_name)[1][1:].lower() if "." in file_name else ""

        try:
            mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat() if os.path.exists(file_path) else None
        except Exception:
            mod_time = None

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO metadata (file_path, file_name, file_size_formatted, file_type, extracted_at, modified_on, full_metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_path,
                    file_name,
                    file_size_formatted,
                    file_type,
                    datetime.now().isoformat(),
                    mod_time,
                    json.dumps(metadata),
                ),
            )
            conn.commit()
            record_id = cursor.lastrowid
            cursor.execute("SELECT * FROM metadata WHERE id=?", (record_id,))
            return cursor.fetchone()

    def fetch_metadata_by_id(self, record_id):
        """Retrieve a metadata record by its database ID.
        
        Args:
            record_id (int): Database ID of the metadata record.
            
        Returns:
            tuple: Database row with all metadata fields, or None if not found.
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM metadata WHERE id=?", (record_id,))
            return cursor.fetchone()

    def fetch_all_metadata(self):
        """Retrieve all metadata records from the database.
        
        Returns:
            list: List of tuples, each containing a complete metadata record.
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM metadata")
            return cursor.fetchall()

    def fetch_latest_by_path(self, path: str):
        """Retrieve the most recent metadata record for a given file path.
        
        Args:
            path (str): File path to search for.
            
        Returns:
            tuple: Most recent metadata record for the file, or None if not found.
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM metadata WHERE file_path = ? ORDER BY id DESC LIMIT 1", (path,))
            return cursor.fetchone()

    def fetch_all_metadata_formatted(self):
        """Retrieve formatted metadata (without full_metadata JSON) for all records.
        
        Returns:
            list: List of tuples with select columns for display/export.
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, file_path, file_name, file_size_formatted, file_type, extracted_at FROM metadata")
            return cursor.fetchall()

    def get_recent_records(self, limit: int = 10):
        """Retrieve the most recent metadata records.
        
        Args:
            limit (int): Maximum number of records to return (default: 10).
            
        Returns:
            list: List of metadata records sorted by extraction time (newest first).
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM metadata ORDER BY extracted_at DESC, id DESC LIMIT ?",
                (limit,),
            )
            return cursor.fetchall()

    def get_database_stats(self):
        """Calculate statistics about metadata records in the database.
        
        Returns:
            dict: Dictionary with 'total_records' count and 'file_types' breakdown.
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM metadata")
            total_records = cursor.fetchone()[0]
            cursor.execute("SELECT file_type, COUNT(*) FROM metadata GROUP BY file_type")
            type_counts = cursor.fetchall()
        return {"total_records": total_records, "file_types": dict(type_counts)}

    def clear_metadata(self):
        """Delete all metadata records from the database.
        
        Returns:
            bool: True if deletion succeeded, False if an error occurred.
        """
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM metadata")
                conn.commit()
            return True
        except Exception as e:
            print(f"Error clearing metadata: {e}")
            return False

    def delete_record(self, record_id):
        """Delete a specific metadata record by ID.
        
        Args:
            record_id (int): Database ID of the record to delete.
            
        Returns:
            bool: True if deletion succeeded, False otherwise.
        """
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM metadata WHERE id=?", (record_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting record: {e}")
            return False

    def filter_and_search_data(self, search_term: str, file_type_filter: str, date_filter: str, sort_option: str):
        """Filter and search metadata records with multiple criteria.
        
        Args:
            search_term (str): Search term to find in file name or path.
            file_type_filter (str): File type filter (e.g., 'pdf', 'All').
            date_filter (str): Date range filter ('All Time', 'Today', 'This Week', 'This Month', 'Last 30 Days').
            sort_option (str): Sorting option ('Date (Newest)', 'Name (A-Z)', etc.).
            
        Returns:
            list: Filtered and sorted metadata records matching the criteria.
        """
        with self._connect() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM metadata WHERE 1=1"
            params = []

            term = (search_term or "").strip()
            if term:
                query += " AND (file_name LIKE ? OR file_path LIKE ?)"
                pattern = f"%{term}%"
                params.extend([pattern, pattern])

            if file_type_filter and file_type_filter != "All":
                query += " AND file_type = ?"
                params.append(file_type_filter)

            if date_filter and date_filter != "All Time":
                now = datetime.now()
                if date_filter == "Today":
                    start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                elif date_filter == "This Week":
                    start_date = now - timedelta(days=now.weekday())
                    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
                elif date_filter == "This Month":
                    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                elif date_filter == "Last 30 Days":
                    start_date = now - timedelta(days=30)
                else:
                    start_date = None
                if start_date:
                    query += " AND extracted_at >= ?"
                    params.append(start_date.isoformat())

            if sort_option == "Date (Newest)":
                query += " ORDER BY extracted_at DESC"
            elif sort_option == "Date (Oldest)":
                query += " ORDER BY extracted_at ASC"
            elif sort_option == "Name (A-Z)":
                query += " ORDER BY file_name ASC"
            elif sort_option == "Name (Z-A)":
                query += " ORDER BY file_name DESC"
            elif sort_option == "Size (Largest)":
                query += " ORDER BY LENGTH(file_size_formatted) DESC, file_size_formatted DESC"
            elif sort_option == "Size (Smallest)":
                query += " ORDER BY LENGTH(file_size_formatted) ASC, file_size_formatted ASC"

            cursor.execute(query, params)
            return cursor.fetchall()

    def export_data(self, format_type: str, data):
        """Export metadata records to various file formats.
        
        Args:
            format_type (str): Export format ('json', 'xml', 'excel', 'csv', 'pdf').
            data (list): List of metadata records to export.
            
        Returns:
            bool: True if export succeeded, False if no data provided.
        """
        if not data:
            return False

        df = pd.DataFrame(
            data,
            columns=[
                "ID",
                "File Path",
                "File Name",
                "File Size",
                "File Type",
                "Extracted At",
                "Modified On",
                "Full Metadata",
            ],
        )

        if format_type == "json":
            self.reporter.export_to_json(df)
        elif format_type == "xml":
            self.reporter.export_to_xml(df)
        elif format_type == "excel":
            self.reporter.export_to_excel(df)
        elif format_type == "csv":
            self.reporter.export_to_csv(data)
        elif format_type == "pdf":
            self.reporter.export_to_pdf(df)
        return True

    def save_edited_metadata(self, file_path, payload):
        """Save edited metadata as a new database record.
        
        Args:
            file_path (str): Path to the original file.
            payload (dict): Dictionary with 'metadata' key containing edited metadata.
            
        Returns:
            tuple: (bool, str) - Success status and message.
        """
        try:
            metadata = (payload or {}).get("metadata", {})
            if not isinstance(metadata, dict) or not metadata:
                return False, "No edited metadata provided."

            file_name = os.path.basename(file_path) if file_path else ""
            try:
                size_bytes = os.path.getsize(file_path) if file_path and os.path.exists(file_path) else 0
            except Exception:
                size_bytes = 0
            file_size_formatted = self.format_file_size(size_bytes)
            file_type = os.path.splitext(file_name)[1][1:].lower() if "." in file_name else ""

            try:
                mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat() if file_path and os.path.exists(file_path) else None
            except Exception:
                mod_time = None

            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO metadata (file_path, file_name, file_size_formatted, file_type, extracted_at, modified_on, full_metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_path,
                        file_name,
                        file_size_formatted,
                        file_type,
                        datetime.now().isoformat(),
                        mod_time,
                        json.dumps(metadata),
                    ),
                )
                conn.commit()
            return True, "Edited metadata saved to database."
        except Exception as e:
            return False, f"DB save failed: {str(e)}"

    def optimize_database(self):
        """Optimize the SQLite database for better performance.
        
        Returns:
            bool: True if optimization succeeded, False if an error occurred.
        """
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA optimize;")
                conn.commit()
            return True
        except Exception as e:
            print(f"Error optimizing database: {e}")
            return False


# Singleton instance and compatibility wrappers --------------------------------
db_manager = MetadataDatabase()


def db_init():
    """Initialize database tables. Wrapper around db_manager._ensure_tables()."""
    return db_manager._ensure_tables()


def format_file_size(size_bytes):
    """Wrapper: Convert file size to human-readable format."""
    return db_manager.format_file_size(size_bytes)


def insert_metadata(file_path, metadata):
    """Wrapper: Insert metadata record for a file."""
    return db_manager.insert_metadata(file_path, metadata)


def fetch_metadata_by_id(record_id):
    """Wrapper: Retrieve metadata record by ID."""
    return db_manager.fetch_metadata_by_id(record_id)


def fetch_all_metadata():
    """Wrapper: Retrieve all metadata records."""
    return db_manager.fetch_all_metadata()


def fetch_latest_by_path(path: str):
    """Wrapper: Retrieve most recent metadata for a file path."""
    return db_manager.fetch_latest_by_path(path)


def fetch_all_metadata_formatted():
    """Wrapper: Retrieve formatted metadata for all records."""
    return db_manager.fetch_all_metadata_formatted()


def get_recent_records(limit: int = 10):
    """Wrapper: Retrieve recent metadata records."""
    return db_manager.get_recent_records(limit)


def get_database_stats():
    """Wrapper: Get database statistics."""
    return db_manager.get_database_stats()


def clear_metadata():
    """Wrapper: Delete all metadata records."""
    return db_manager.clear_metadata()


def delete_record(record_id):
    """Wrapper: Delete a specific metadata record."""
    return db_manager.delete_record(record_id)


def filter_and_search_data(search_term: str, file_type_filter: str, date_filter: str, sort_option: str):
    """Wrapper: Filter and search metadata with criteria."""
    return db_manager.filter_and_search_data(search_term, file_type_filter, date_filter, sort_option)


def export_data(format_type: str, data):
    """Wrapper: Export metadata to various formats."""
    return db_manager.export_data(format_type, data)


def save_edited_metadata(file_path, payload):
    """Wrapper: Save edited metadata to database."""
    return db_manager.save_edited_metadata(file_path, payload)


def optimize_database():
    """Wrapper: Optimize the SQLite database."""
    return db_manager.optimize_database()
