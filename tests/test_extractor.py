"""Unit tests for MetadataExtractor across multiple file formats."""

import os
import sys
import json
import csv
import sqlite3
import wave
import zipfile
import tarfile
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / 'src'
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pytest
from PyPDF2 import PdfWriter
from PIL import Image, PngImagePlugin

from extractor import (
    MetadataExtractor,
    extract_pdf_metadata,
    extract_image_metadata,
    extract_audio_metadata,
    extract_office_metadata,
    extract_archive_metadata,
    extract_structured_metadata,
    extract_code_metadata,
    extract_database_metadata,
    extract_video_metadata,
    extract_text_metadata,
    extract_generic_metadata,
    extract,
    extract_and_store,
    batch_extract,
)


class DummyDB:
    """In-memory stub used to capture insert calls."""

    def __init__(self):
        self.saved = []

    def insert_metadata(self, file_path, metadata):
        entry = {"file_path": str(file_path), "metadata": metadata}
        self.saved.append(entry)
        return (len(self.saved), file_path, os.path.basename(file_path), "1.0 KB", "txt", "2024-01-01", "2024-01-01", "")


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


# =====================================================================
# 1. Initialization & Path Validation Tests
# =====================================================================
def test_metadata_extractor_init():
    """Test extractor initialization."""
    extractor_obj = MetadataExtractor()
    assert extractor_obj is not None
    assert extractor_obj.db_client is not None


def test_extractor_with_custom_db():
    """Test extractor with custom database client."""
    db_client = DummyDB()
    extractor_obj = MetadataExtractor(db_client=db_client)
    assert extractor_obj.db_client == db_client


def test_validate_file_path_valid(temp_dir):
    """Test file path validation with valid file."""
    test_file = os.path.join(temp_dir, "test.txt")
    with open(test_file, "w") as f:
        f.write("test content")

    is_valid, error = MetadataExtractor._validate_file_path(test_file)
    assert is_valid is True
    assert error == ""


def test_validate_file_path_missing_file():
    """Test file path validation with missing file."""
    is_valid, error = MetadataExtractor._validate_file_path("/nonexistent/path/file.txt")
    assert is_valid is False
    assert "File not found" in error


def test_validate_file_path_empty():
    """Test file path validation with empty path."""
    is_valid, error = MetadataExtractor._validate_file_path("")
    assert is_valid is False
    assert "No file path provided" in error


def test_validate_file_path_directory(temp_dir):
    """Test file path validation with directory instead of file."""
    is_valid, error = MetadataExtractor._validate_file_path(temp_dir)
    assert is_valid is False
    assert "not a file" in error


# =====================================================================
# 2. Text & Code Extraction Tests
# =====================================================================
def test_extract_text_metadata(temp_dir):
    """Test text metadata extraction."""
    test_file = os.path.join(temp_dir, "sample.txt")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("first line\nsecond line\n")

    extractor_obj = MetadataExtractor()
    meta = extractor_obj.extract_text_metadata(test_file)

    assert meta["Line Count"] == 2
    assert meta["Encoding"] == "utf-8"
    assert meta["File Size (bytes)"] > 0


def test_extract_code_metadata_python(temp_dir):
    """Test code metadata extraction for Python files."""
    test_file = os.path.join(temp_dir, "sample.py")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("# This is a comment\n\ndef hello():\n    print('world')\n")

    meta = extract_code_metadata(test_file)
    assert meta["Language"] == "Python"
    assert meta["Total Lines"] == 4
    assert meta["Comment Lines"] == 1
    assert meta["Blank Lines"] == 1
    assert meta["Code Lines (SLOC)"] == 2


def test_extract_code_metadata_javascript(temp_dir):
    """Test code metadata extraction for JavaScript / C-style comments."""
    test_file = os.path.join(temp_dir, "sample.js")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("// JS comment\nfunction test() {\n    return 42;\n}\n")

    meta = extract(test_file)
    assert meta["Language"] == "JavaScript"
    assert meta["Comment Lines"] == 1
    assert meta["Code Lines (SLOC)"] == 3


def test_extract_code_metadata_markdown_with_frontmatter(temp_dir):
    """Test Markdown extraction with YAML frontmatter."""
    test_file = os.path.join(temp_dir, "doc.md")
    content = "---\ntitle: Sample Title\nauthor: Alice\n---\n# Main Heading\n\nSome text content.\n```python\nprint(1)\n```\n"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(content)

    meta = extract(test_file)
    assert meta["Language"] == "Markdown"
    assert meta["Header Count"] == 1
    assert meta["Code Blocks Count"] == 1
    assert meta.get("Frontmatter Title") == "Sample Title"
    assert meta.get("Frontmatter Author") == "Alice"


# =====================================================================
# 3. PDF Extraction Tests
# =====================================================================
def test_extract_pdf_metadata(temp_dir):
    """Test PDF metadata extraction."""
    pdf_path = os.path.join(temp_dir, "sample.pdf")
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_metadata({"/Title": "Sample Title", "/Author": "Test Author"})
    with open(pdf_path, "wb") as f:
        writer.write(f)

    extractor_obj = MetadataExtractor()
    meta = extractor_obj.extract_pdf_metadata(pdf_path)

    assert meta.get("Pages") == 1
    assert meta.get("Title") == "Sample Title"
    assert meta.get("Author") == "Test Author"


def test_extract_pdf_metadata_missing_file():
    """Test PDF extraction with missing file."""
    extractor_obj = MetadataExtractor()
    meta = extractor_obj.extract_pdf_metadata("/nonexistent/file.pdf")
    assert "Error" in meta
    assert "File not found" in meta["Error"]


# =====================================================================
# 4. Image Extraction Tests (PNG, JPEG, GIF, SVG)
# =====================================================================
def test_extract_image_metadata_png(temp_dir):
    """Test PNG image metadata extraction including dimensions and text chunks."""
    png_path = os.path.join(temp_dir, "test.png")
    img = Image.new("RGBA", (100, 50), color="blue")
    meta_info = PngImagePlugin.PngInfo()
    meta_info.add_text("Author", "Test Photographer")
    meta_info.add_text("Title", "Blue Banner")
    img.save(png_path, "PNG", pnginfo=meta_info)

    meta = extract_image_metadata(png_path)
    assert meta.get("Format") == "PNG"
    assert meta.get("Width") == 100
    assert meta.get("Height") == 50
    assert meta.get("Dimensions") == "100 x 50"
    assert meta.get("Author") == "Test Photographer"
    assert meta.get("Title") == "Blue Banner"


def test_extract_image_metadata_jpeg_auto_detect(temp_dir):
    """Test JPEG auto-detection and dimension calculation."""
    jpg_path = os.path.join(temp_dir, "test.jpg")
    img = Image.new("RGB", (200, 100), color="red")
    img.save(jpg_path, "JPEG")

    meta = extract(jpg_path)
    assert meta.get("Format") == "JPEG"
    assert meta.get("Width") == 200
    assert meta.get("Height") == 100
    assert "Megapixels" in meta


def test_extract_image_metadata_svg(temp_dir):
    """Test SVG vector image metadata extraction."""
    svg_path = os.path.join(temp_dir, "vector.svg")
    svg_content = '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="150" viewBox="0 0 300 150"><title>Vector Diagram</title><circle cx="50" cy="50" r="40"/></svg>'
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

    meta = extract(svg_path)
    assert meta.get("Format") == "SVG Vector Graphic"
    assert meta.get("Width") == "300"
    assert meta.get("Height") == "150"
    assert meta.get("Title") == "Vector Diagram"
    assert meta.get("ViewBox") == "0 0 300 150"


# =====================================================================
# 5. Audio Extraction Tests (WAV, MP3)
# =====================================================================
def test_extract_audio_metadata_wav(temp_dir):
    """Test WAV audio metadata extraction."""
    wav_path = os.path.join(temp_dir, "sound.wav")
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(2)  # Stereo
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(44100)
        wf.writeframes(b"\x00\x00" * 44100)  # 1 second of silence

    meta = extract_audio_metadata(wav_path)
    assert meta.get("Audio Format") == "WAV (RIFF Waveform Audio)"
    assert meta.get("Channels") == "2 (Stereo)"
    assert "44100 Hz" in meta.get("Sample Rate", "")
    assert meta.get("Bits Per Sample") == "16-bit"


# =====================================================================
# 6. Office & OpenDocument Extraction Tests (DOCX, XLSX, OpenXML)
# =====================================================================
def test_extract_office_metadata_docx(temp_dir):
    """Test Word DOCX metadata extraction."""
    import docx

    docx_path = os.path.join(temp_dir, "test.docx")
    doc = docx.Document()
    doc.core_properties.title = "Office Report"
    doc.core_properties.author = "Jane Doe"
    doc.add_paragraph("First paragraph text")
    doc.add_paragraph("Second paragraph text")
    doc.save(docx_path)

    meta = extract_office_metadata(docx_path)
    assert meta.get("Document Format") == "Microsoft Word (DOCX)"
    assert meta.get("Title") == "Office Report"
    assert meta.get("Author") == "Jane Doe"
    assert meta.get("Paragraph Count") == 2


def test_extract_office_metadata_xlsx(temp_dir):
    """Test Excel XLSX metadata extraction."""
    import openpyxl

    xlsx_path = os.path.join(temp_dir, "test.xlsx")
    wb = openpyxl.Workbook()
    wb.properties.title = "Financials 2026"
    wb.properties.creator = "Finance Team"
    ws = wb.active
    ws.title = "Summary"
    wb.create_sheet(title="Details")
    wb.save(xlsx_path)

    meta = extract(xlsx_path)
    assert meta.get("Document Format") == "Microsoft Excel (XLSX)"
    assert meta.get("Title") == "Financials 2026"
    assert meta.get("Creator") == "Finance Team"
    assert meta.get("Total Sheets") == 2
    assert "Summary" in meta.get("Sheet Names", "")


def test_extract_office_metadata_openxml_pptx(temp_dir):
    """Test PowerPoint PPTX extraction via OpenXML package zip parser."""
    pptx_path = os.path.join(temp_dir, "presentation.pptx")
    core_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                       xmlns:dc="http://purl.org/dc/elements/1.1/"
                       xmlns:dcterms="http://purl.org/dc/terms/">
        <dc:title>Q3 Strategy</dc:title>
        <dc:creator>Marketing Lead</dc:creator>
        <cp:revision>3</cp:revision>
    </cp:coreProperties>"""

    app_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
        <Slides>15</Slides>
        <Application>Microsoft PowerPoint</Application>
    </Properties>"""

    with zipfile.ZipFile(pptx_path, "w") as zf:
        zf.writestr("docProps/core.xml", core_xml)
        zf.writestr("docProps/app.xml", app_xml)

    meta = extract(pptx_path)
    assert meta.get("Document Format") == "Microsoft PowerPoint (PPTX)"
    assert meta.get("Title") == "Q3 Strategy"
    assert meta.get("Creator") == "Marketing Lead"
    assert meta.get("Revision") == "3"
    assert meta.get("Slides") == "15"


# =====================================================================
# 7. Archive Extraction Tests (ZIP, TAR)
# =====================================================================
def test_extract_archive_metadata_zip(temp_dir):
    """Test ZIP archive metadata extraction."""
    zip_path = os.path.join(temp_dir, "bundle.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("file1.txt", "Hello World")
        zf.writestr("data/file2.json", '{"status": "ok"}')
        zf.comment = b"Release bundle"

    meta = extract_archive_metadata(zip_path)
    assert meta.get("Archive Format") == "ZIP Archive"
    assert meta.get("Total Files") == 2
    assert meta.get("Archive Comment") == "Release bundle"
    assert "file1.txt" in meta.get("Sample Files", "")


def test_extract_archive_metadata_tar(temp_dir):
    """Test TAR archive metadata extraction."""
    tar_path = os.path.join(temp_dir, "archive.tar")
    file1 = os.path.join(temp_dir, "tar_sub1.txt")
    with open(file1, "w") as f:
        f.write("tar test content")

    with tarfile.open(tar_path, "w") as tf:
        tf.add(file1, arcname="tar_sub1.txt")

    meta = extract(tar_path)
    assert meta.get("Archive Format") == "TAR Archive Container"
    assert meta.get("Total Files") == 1


# =====================================================================
# 8. Structured Data Extraction Tests (JSON, CSV, XML, YAML, INI, SQL)
# =====================================================================
def test_extract_structured_metadata_json(temp_dir):
    """Test JSON structured data extraction."""
    json_path = os.path.join(temp_dir, "config.json")
    data = {"database": {"host": "localhost", "port": 5432}, "debug": True, "version": "1.0"}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    meta = extract_structured_metadata(json_path)
    assert meta.get("Data Format") == "JSON (JavaScript Object Notation)"
    assert meta.get("Root Type") == "Object (Dictionary)"
    assert meta.get("Top-Level Keys Count") == 3
    assert "database" in meta.get("Top-Level Keys", "")


def test_extract_structured_metadata_csv(temp_dir):
    """Test CSV structured data extraction."""
    csv_path = os.path.join(temp_dir, "users.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "email", "role"])
        writer.writerow([1, "Alice", "alice@example.com", "Admin"])
        writer.writerow([2, "Bob", "bob@example.com", "User"])

    meta = extract(csv_path)
    assert "CSV" in meta.get("Data Format", "")
    assert meta.get("Total Rows") == 3
    assert meta.get("Total Columns") == 4
    assert "id, name, email, role" in meta.get("Header Columns", "")


def test_extract_structured_metadata_ini(temp_dir):
    """Test INI configuration file extraction."""
    ini_path = os.path.join(temp_dir, "settings.ini")
    content = "[Server]\nhost=127.0.0.1\nport=8080\n\n[Security]\nssl=true\n"
    with open(ini_path, "w", encoding="utf-8") as f:
        f.write(content)

    meta = extract(ini_path)
    assert meta.get("Data Format") == "Configuration File"
    assert meta.get("Section Count") == 2
    assert "Server" in meta.get("Sections", "")


def test_extract_structured_metadata_sql(temp_dir):
    """Test SQL script file metadata extraction."""
    sql_path = os.path.join(temp_dir, "schema.sql")
    content = "CREATE TABLE users (id INT, name TEXT);\nCREATE TABLE logs (id INT, msg TEXT);\n"
    with open(sql_path, "w", encoding="utf-8") as f:
        f.write(content)

    meta = extract(sql_path)
    assert meta.get("Data Format") == "SQL Database Script"
    assert meta.get("Table Count") == 2
    assert "users" in meta.get("Tables Defined", "")


# =====================================================================
# 9. Database Extraction Tests (SQLite)
# =====================================================================
def test_extract_database_metadata_sqlite(temp_dir):
    """Test SQLite database file extraction."""
    db_path = os.path.join(temp_dir, "app_data.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);")
    cur.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INT, amount REAL);")
    cur.execute("CREATE VIEW customer_orders AS SELECT * FROM customers JOIN orders ON customers.id = orders.customer_id;")
    cur.execute("CREATE INDEX idx_customers_name ON customers (name);")
    cur.execute("PRAGMA user_version = 42;")
    conn.commit()
    conn.close()

    meta = extract_database_metadata(db_path)
    assert meta.get("Database Engine") == "SQLite 3"
    assert meta.get("Table Count") == 2
    assert "customers" in meta.get("Tables", "")
    assert meta.get("View Count") == 1
    assert "customer_orders" in meta.get("Views", "")
    assert meta.get("Index Count") == 1
    assert meta.get("User Version") == 42


# =====================================================================
# 10. Generic Binary Fallback Tests
# =====================================================================
def test_extract_generic_metadata_binary(temp_dir):
    """Test generic extraction computing SHA-256 and MD5 for binary file."""
    bin_path = os.path.join(temp_dir, "data.bin")
    data = b"\x00\x01\x02\x03\x04\x05\x06\x07" * 32
    with open(bin_path, "wb") as f:
        f.write(data)

    meta = extract_generic_metadata(bin_path)
    assert "SHA-256 Checksum" in meta
    assert len(meta["SHA-256 Checksum"]) == 64
    assert "MD5 Checksum" in meta
    assert len(meta["MD5 Checksum"]) == 32
    assert meta.get("File Name") == "data.bin"


# =====================================================================
# 11. Persistence & Batch Extraction Tests
# =====================================================================
def test_extract_and_store(temp_dir):
    """Test extract and store functionality."""
    test_file = os.path.join(temp_dir, "sample.txt")
    with open(test_file, "w") as f:
        f.write("test content\nline 2\n")

    db_client = DummyDB()
    extractor_obj = MetadataExtractor(db_client=db_client)

    meta, db_row = extractor_obj.extract_and_store(test_file)
    assert "Line Count" in meta
    assert db_row is not None
    assert len(db_client.saved) == 1


def test_extract_and_store_with_error(temp_dir):
    """Test extract and store with extraction failure."""
    db_client = DummyDB()
    extractor_obj = MetadataExtractor(db_client=db_client)

    meta, db_row = extractor_obj.extract_and_store("/nonexistent/file.txt")
    assert "Error" in meta
    assert db_row is None


def test_batch_extract_reports_success_and_failure(temp_dir):
    """Test batch extraction with success and failure."""
    db_client = DummyDB()
    extractor_obj = MetadataExtractor(db_client=db_client)

    good = os.path.join(temp_dir, "good.txt")
    with open(good, "w") as f:
        f.write("hello\nworld\n")

    missing = os.path.join(temp_dir, "missing.txt")
    progress_messages = []

    result = extractor_obj.batch_extract(
        [good, missing],
        progress_callback=lambda message, progress: progress_messages.append((message, progress)),
    )

    assert result["successful"] == 1
    assert result["failed"] == 1
    assert result["total"] == 2
    assert len(db_client.saved) == 1
    assert any("Processing" in msg[0] for msg in progress_messages)


def test_wrapper_functions(temp_dir):
    """Test module-level wrapper functions."""
    test_file = os.path.join(temp_dir, "test.txt")
    with open(test_file, "w") as f:
        f.write("hello\nworld\n")

    result = extract(test_file)
    assert "Line Count" in result

    batch_result = batch_extract([test_file])
    assert batch_result["total"] == 1
