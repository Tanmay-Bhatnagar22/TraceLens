import sys
from pathlib import Path
import tempfile
import os
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / 'src'
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pytest
from db import (
    MetadataDatabase, format_file_size, insert_metadata, fetch_metadata_by_id,
    fetch_all_metadata, fetch_latest_by_path, get_database_stats, clear_metadata,
    delete_record, filter_and_search_data, export_data, optimize_database
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_metadata.db")
        db = MetadataDatabase(db_path=db_path)
        yield db


@pytest.fixture
def sample_metadata():
    """Sample metadata dictionary for testing."""
    return {
        "Title": "Test Document",
        "Author": "Test Author",
        "Pages": 10
    }


@pytest.fixture
def sample_file(tmp_path):
    """Create a sample test file."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("Sample content")
    return str(test_file)


def test_metadata_database_init():
    """Test database initialization."""
    db = MetadataDatabase()
    assert db is not None
    assert os.path.basename(db.db_path) == "file_metadata.db"


def test_format_file_size():
    """Test file size formatting with various sizes."""
    assert format_file_size(0) == "0 B"
    assert format_file_size(1024) == "1.00 KB"
    assert format_file_size(1024 * 1024) == "1.00 MB"
    assert format_file_size(1024 * 1024 * 1024) == "1.00 GB"
    assert format_file_size(512) == "512.00 B"  # Less than 1 KB stays as bytes


def test_insert_metadata(temp_db, sample_file, sample_metadata):
    """Test inserting metadata into database."""
    result = temp_db.insert_metadata(sample_file, sample_metadata)
    assert result is not None
    assert result[1] == sample_file  # file_path
    assert result[2] == "test.txt"  # file_name


def test_fetch_metadata_by_id(temp_db, sample_file, sample_metadata):
    """Test fetching metadata by record ID."""
    inserted = temp_db.insert_metadata(sample_file, sample_metadata)
    record_id = inserted[0]
    
    fetched = temp_db.fetch_metadata_by_id(record_id)
    assert fetched is not None
    assert fetched[0] == record_id
    assert fetched[1] == sample_file


def test_fetch_all_metadata(temp_db, sample_file, sample_metadata):
    """Test fetching all metadata records."""
    temp_db.insert_metadata(sample_file, sample_metadata)
    temp_db.insert_metadata(sample_file, sample_metadata)
    
    all_records = temp_db.fetch_all_metadata()
    assert len(all_records) >= 2


def test_fetch_latest_by_path(temp_db, sample_file, sample_metadata):
    """Test fetching latest metadata record by file path."""
    temp_db.insert_metadata(sample_file, sample_metadata)
    
    latest = temp_db.fetch_latest_by_path(sample_file)
    assert latest is not None
    assert latest[1] == sample_file


def test_fetch_all_metadata_formatted(temp_db, sample_file, sample_metadata):
    """Test fetching formatted metadata."""
    temp_db.insert_metadata(sample_file, sample_metadata)
    
    formatted = temp_db.fetch_all_metadata_formatted()
    assert len(formatted) >= 1
    assert formatted[0][1] == sample_file  # file_path


def test_get_recent_records(temp_db, sample_file, sample_metadata):
    """Test fetching recent records."""
    temp_db.insert_metadata(sample_file, sample_metadata)
    
    recent = temp_db.get_recent_records(limit=5)
    assert len(recent) >= 1


def test_get_database_stats(temp_db, sample_file, sample_metadata):
    """Test getting database statistics."""
    temp_db.insert_metadata(sample_file, sample_metadata)
    
    stats = temp_db.get_database_stats()
    assert "total_records" in stats
    assert "file_types" in stats
    assert stats["total_records"] >= 1


def test_delete_record(temp_db, sample_file, sample_metadata):
    """Test deleting a record."""
    inserted = temp_db.insert_metadata(sample_file, sample_metadata)
    record_id = inserted[0]
    
    success = temp_db.delete_record(record_id)
    assert success is True
    
    fetched = temp_db.fetch_metadata_by_id(record_id)
    assert fetched is None


def test_delete_nonexistent_record(temp_db):
    """Test deleting a non-existent record."""
    success = temp_db.delete_record(9999)
    assert success is False


def test_clear_metadata(temp_db, sample_file, sample_metadata):
    """Test clearing all metadata."""
    temp_db.insert_metadata(sample_file, sample_metadata)
    
    success = temp_db.clear_metadata()
    assert success is True
    
    all_records = temp_db.fetch_all_metadata()
    assert len(all_records) == 0


def test_filter_and_search_data(temp_db, sample_file, sample_metadata):
    """Test filtering and searching data."""
    temp_db.insert_metadata(sample_file, sample_metadata)
    
    results = temp_db.filter_and_search_data("test", "All", "All Time", "Date (Newest)")
    assert len(results) >= 1


def test_filter_by_file_type(temp_db, sample_file, sample_metadata):
    """Test filtering by file type."""
    temp_db.insert_metadata(sample_file, sample_metadata)
    
    results = temp_db.filter_and_search_data("", "txt", "All Time", "Date (Newest)")
    assert len(results) >= 1


def test_save_edited_metadata(temp_db, sample_file):
    """Test saving edited metadata."""
    payload = {"metadata": {"Title": "Updated Title", "Author": "New Author"}}
    
    success, message = temp_db.save_edited_metadata(sample_file, payload)
    assert success is True


def test_save_edited_metadata_with_empty_metadata(temp_db, sample_file):
    """Test saving with empty metadata."""
    payload = {"metadata": {}}
    
    success, message = temp_db.save_edited_metadata(sample_file, payload)
    assert success is False


def test_optimize_database(temp_db):
    """Test database optimization."""
    success = temp_db.optimize_database()
    assert success is True


def test_wrapper_functions(sample_file, sample_metadata):
    """Test module-level wrapper functions."""
    # Test insert_metadata wrapper
    result = insert_metadata(sample_file, sample_metadata)
    assert result is not None
    
    # Test fetch_metadata_by_id wrapper
    record_id = result[0]
    fetched = fetch_metadata_by_id(record_id)
    assert fetched is not None
    
    # Test fetch_all_metadata wrapper
    all_records = fetch_all_metadata()
    assert isinstance(all_records, list)
    
    # Test get_database_stats wrapper
    stats = get_database_stats()
    assert isinstance(stats, dict)
