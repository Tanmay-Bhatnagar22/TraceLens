from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PyPDF2 import PdfReader
import mimetypes
import os
from typing import Any, Callable, Iterable
import db


class MetadataExtractor:
    """Object-oriented metadata extractor with optional DB persistence.
    
    Supports extraction from PDF, text files, and other file types using 
    hachoir and PyPDF2 libraries. Can optionally persist extracted metadata to database.
    """

    def __init__(self, db_client: db.MetadataDatabase | None = None) -> None:
        self.db_client = db_client or db.db_manager

    @staticmethod
    def _validate_file_path(file_path: str) -> tuple[bool, str]:
        """Validate that the provided path exists and is a file.
        
        Args:
            file_path (str): Path to validate.
            
        Returns:
            tuple: (bool, str) - (is_valid, error_message)
        """
        if not file_path:
            return False, "No file path provided."
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        if not os.path.isfile(file_path):
            return False, f"Path is not a file: {file_path}"
        return True, ""

    def extract_pdf_metadata(self, file_path: str) -> dict[str, Any]:
        """Extract metadata from a PDF file.
        
        Args:
            file_path (str): Path to the PDF file.
            
        Returns:
            dict: Dictionary with extracted metadata, or {'Error': message} if extraction fails.
        """
        is_valid, error = self._validate_file_path(file_path)
        if not is_valid:
            return {"Error": error}

        try:
            reader = PdfReader(file_path)
            info = reader.metadata or {}
            meta_dict = {k[1:]: v for k, v in info.items()}
            meta_dict["Pages"] = len(reader.pages)
            return meta_dict
        except Exception as e:
            return {"Error": f"PDF extraction failed: {e}"}

    def extract_text_metadata(self, file_path: str) -> dict[str, Any]:
        """Extract metadata from a text file.
        
        Args:
            file_path (str): Path to the text file.
            
        Returns:
            dict: Dictionary with file size, line count, and encoding, or {'Error': message} on failure.
        """
        is_valid, error = self._validate_file_path(file_path)
        if not is_valid:
            return {"Error": error}

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            stat = os.stat(file_path)
            return {"File Size (bytes)": stat.st_size, "Line Count": len(lines), "Encoding": "utf-8"}
        except Exception as e:
            return {"Error": f"Text extraction failed: {e}"}

    def extract(self, file_path: str) -> dict[str, Any]:
        """Extract metadata from any supported file type.
        
        Automatically detects file type and uses appropriate extraction method
        (PDF, text, or hachoir parser for media files).
        
        Args:
            file_path (str): Path to the file.
            
        Returns:
            dict: Extracted metadata dictionary, or {'Error': message} on failure.
        """
        is_valid, error = self._validate_file_path(file_path)
        if not is_valid:
            return {"Error": error}

        mime_type, _ = mimetypes.guess_type(file_path)
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf" or (mime_type and mime_type == "application/pdf"):
            return self.extract_pdf_metadata(file_path)

        text_exts = {".py", ".txt", ".cpp", ".c", ".java", ".js", ".json", ".csv", ".md", ".html", ".css"}
        if ext in text_exts or (mime_type and mime_type.startswith("text")):
            return self.extract_text_metadata(file_path)

        try:
            parser = createParser(file_path)
            if not parser:
                return {"Error": "Unable to parse the file (unsupported or corrupted)."}
            metadata = extractMetadata(parser)
            if not metadata:
                return {"Error": "No metadata found."}
            meta_dict = {}
            for item in metadata.exportPlaintext():
                if ": " in item:
                    key, value = item.split(": ", 1)
                    meta_dict[key.strip()] = value.strip()
            return meta_dict
        except Exception as e:
            return {"Error": f"An error occurred: {e}"}

    def extract_and_store(self, file_path: str) -> tuple[dict[str, Any], Any]:
        """Extract metadata from file and store in database.
        
        Args:
            file_path (str): Path to the file.
            
        Returns:
            tuple: (metadata_dict, db_row) - Extracted metadata and database record,
                   or (error_dict, None) if extraction/storage fails.
        """
        metadata = self.extract(file_path)
        db_row = None

        if not metadata or not isinstance(metadata, dict):
            return {"Error": "Extraction returned no metadata."}, None

        if "Error" in metadata:
            return metadata, None

        try:
            db_row = self.db_client.insert_metadata(file_path, metadata)
        except Exception as exc:
            metadata = {**metadata, "Error": f"Failed to persist metadata: {exc}"}
            db_row = None

        return metadata, db_row

    def batch_extract(self, file_paths: Iterable[str], progress_callback: Callable[[str, float], None] | None = None) -> dict[str, Any]:
        """Extract metadata from multiple files with optional progress reporting.
        
        Args:
            file_paths (Iterable[str]): List/iterable of file paths to extract.
            progress_callback (Callable, optional): Callback function(filename, progress_percent) for progress updates.
            
        Returns:
            dict: Summary with 'successful', 'failed', 'total' counts and 'results' list.
        """
        successful_extractions = 0
        failed_extractions = 0
        results = []
        file_paths = list(file_paths)
        total_files = len(file_paths)

        safe_progress_callback = progress_callback
        for i, file_path in enumerate(file_paths):
            try:
                if safe_progress_callback:
                    progress = (i / total_files) * 100 if total_files else 0
                    try:
                        safe_progress_callback(f"Processing: {os.path.basename(file_path)}", progress)
                    except Exception:
                        safe_progress_callback = None

                meta_dict = self.extract(file_path)

                if meta_dict and "Error" not in meta_dict:
                    row = self.db_client.insert_metadata(file_path, meta_dict)
                    results.append({"file_path": file_path, "status": "success", "data": row})
                    successful_extractions += 1
                else:
                    results.append({"file_path": file_path, "status": "failed", "error": meta_dict.get("Error", "Unknown error")})
                    failed_extractions += 1

            except Exception as e:
                results.append({"file_path": file_path, "status": "failed", "error": str(e)})
                failed_extractions += 1

        if safe_progress_callback:
            try:
                safe_progress_callback("Batch extraction completed", 100)
            except Exception:
                pass

        return {"successful": successful_extractions, "failed": failed_extractions, "total": total_files, "results": results}


_extractor = MetadataExtractor()


# Module-level wrapper functions for backward compatibility
def extract_pdf_metadata(file_path):
    """Wrapper: Extract metadata from a PDF file."""
    return _extractor.extract_pdf_metadata(file_path)


def extract_text_metadata(file_path):
    """Wrapper: Extract metadata from a text file."""
    return _extractor.extract_text_metadata(file_path)


def extract(file_path):
    """Wrapper: Extract metadata from any supported file type."""
    return _extractor.extract(file_path)


def extract_and_store(file_path):
    """Wrapper: Extract metadata and store in database."""
    return _extractor.extract_and_store(file_path)


def batch_extract(file_paths, progress_callback=None):
    """Wrapper: Extract metadata from multiple files with optional progress reporting."""
    return _extractor.batch_extract(file_paths, progress_callback)
