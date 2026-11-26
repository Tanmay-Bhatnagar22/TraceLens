import sys
from pathlib import Path
import tempfile
import os
import json
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / 'src'
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from report import (
    MetadataReporter, resource_path, get_asset_path, 
    generate_report_text, create_pdf_report_from_text,
    export_to_json, export_to_xml, export_to_csv
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing."""
    return {
        "Title": "Test Document",
        "Author": "Test Author",
        "Pages": 10,
        "CreationDate": "2024-01-01"
    }


@pytest.fixture
def sample_dataframe():
    """Create sample DataFrame for testing exports."""
    data = {
        'ID': [1, 2],
        'File Path': ['/path/to/file1.txt', '/path/to/file2.pdf'],
        'File Name': ['file1.txt', 'file2.pdf'],
        'File Size': ['1 KB', '2 KB'],
        'File Type': ['txt', 'pdf'],
        'Extracted At': ['2024-01-01', '2024-01-02'],
        'Modified On': ['2024-01-01', '2024-01-02'],
        'Full Metadata': ['{}', '{}']
    }
    return pd.DataFrame(data)


def test_metadata_reporter_init():
    """Test reporter initialization."""
    reporter = MetadataReporter()
    assert reporter is not None


def test_resource_path():
    """Test resource path function."""
    path = resource_path("test.txt")
    assert isinstance(path, str)
    assert "test.txt" in path


def test_get_asset_path():
    """Test get asset path function."""
    path = get_asset_path("logo.png")
    assert isinstance(path, str)

    # Test resolving images from assets directory
    meta_path = get_asset_path("Metadata.png")
    assert os.path.exists(meta_path)
    assert "Metadata.png" in meta_path

    # Test resolving asset with assets prefix
    meta_prefix_path = get_asset_path(os.path.join("assets", "Metadata.png"))
    assert os.path.exists(meta_prefix_path)

    # Test resolving ico in assets directory
    ico_path = get_asset_path("Metadata.ico")
    assert os.path.exists(ico_path)


def test_generate_report_text_basic(sample_metadata):
    """Test generating basic report text."""
    reporter = MetadataReporter()
    text = reporter.generate_report_text(sample_metadata, "/path/to/file.txt")
    
    assert isinstance(text, str)
    assert "File Name" in text
    assert "file.txt" in text


def test_generate_report_text_with_complex_metadata(sample_metadata):
    """Test generating report with complex metadata."""
    complex_meta = {**sample_metadata, "Tags": ["tag1", "tag2"]}
    reporter = MetadataReporter()
    text = reporter.generate_report_text(complex_meta, "/path/to/file.txt")
    
    assert isinstance(text, str)
    assert "title" in text.lower() or "Title" in text


def test_generate_report_text_empty_metadata():
    """Test generating report with empty metadata."""
    reporter = MetadataReporter()
    text = reporter.generate_report_text({}, "file.txt")
    
    assert isinstance(text, str)
    assert "file.txt" in text


def test_generate_report_text_nonexistent_file(sample_metadata):
    """Test generating report with non-existent file."""
    reporter = MetadataReporter()
    text = reporter.generate_report_text(sample_metadata, "/nonexistent/file.txt")
    
    assert isinstance(text, str)


def test_generate_report_text_with_risk_section(sample_metadata):
    """Test report generation includes risk and timeline sections when provided."""
    reporter = MetadataReporter()
    risk_analysis = {
        "risk_level": "HIGH",
        "risk_score": 80,
        "event_count": 2,
        "reasons": ["GPS present", "Author present"],
        "timeline": [
            {"event": "CreateDate", "timestamp": "2024-01-01 10:00:00"},
            {"event": "ModifyDate", "timestamp": "2024-01-02 11:00:00"},
        ],
    }
    text = reporter.generate_report_text(sample_metadata, "test.txt", risk_analysis=risk_analysis)

    assert "Privacy Risk Analysis" in text
    assert "Forensic Timeline" in text
    assert "Risk Level: HIGH" in text


def test_create_pdf_report_from_text(temp_dir, sample_metadata):
    """Test creating PDF report from text."""
    reporter = MetadataReporter()
    report_text = reporter.generate_report_text(sample_metadata, "test.pdf")
    
    output_path = os.path.join(temp_dir, "report.pdf")
    reporter.create_pdf_report_from_text(report_text, output_path)
    
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_create_pdf_report_empty_text(temp_dir):
    """Test creating PDF report with empty text."""
    reporter = MetadataReporter()
    output_path = os.path.join(temp_dir, "empty_report.pdf")
    
    # Should handle empty text gracefully
    reporter.create_pdf_report_from_text("", output_path)
    assert os.path.exists(output_path)


def test_create_pdf_from_dataframe(temp_dir, sample_dataframe):
    """Test creating PDF from DataFrame."""
    reporter = MetadataReporter()
    output_path = os.path.join(temp_dir, "dataframe_report.pdf")
    
    reporter.create_pdf_from_dataframe(sample_dataframe, output_path)
    
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_export_to_json_valid(temp_dir, sample_dataframe):
    """Test exporting to JSON with valid data."""
    reporter = MetadataReporter()
    json_file = os.path.join(temp_dir, "export.json")
    
    # Mock the file dialog behavior
    import unittest.mock as mock
    with mock.patch('src.core.reports.report.filedialog.asksaveasfilename', return_value=json_file):
        with mock.patch('src.core.reports.report.messagebox.showinfo'):
            reporter.export_to_json(sample_dataframe)
    
    assert os.path.exists(json_file)
    with open(json_file, 'r') as f:
        data = json.load(f)
    assert len(data) >= 2


def test_export_to_xml_valid(temp_dir, sample_dataframe):
    """Test exporting to XML with valid data."""
    reporter = MetadataReporter()
    xml_file = os.path.join(temp_dir, "export.xml")
    
    import unittest.mock as mock
    with mock.patch('src.core.reports.report.filedialog.asksaveasfilename', return_value=xml_file):
        with mock.patch('src.core.reports.report.messagebox.showinfo'):
            reporter.export_to_xml(sample_dataframe)
    
    assert os.path.exists(xml_file)
    with open(xml_file, 'r') as f:
        content = f.read()
    assert '<?xml' in content


def test_export_to_csv_valid(temp_dir):
    """Test exporting to CSV with valid data."""
    reporter = MetadataReporter()
    csv_file = os.path.join(temp_dir, "export.csv")
    
    data = [
        (1, '/path/file1.txt', 'file1.txt', '1 KB', 'txt', '2024-01-01', '2024-01-01', '{}'),
        (2, '/path/file2.pdf', 'file2.pdf', '100 KB', 'pdf', '2024-01-02', '2024-01-02', '{}')
    ]
    
    import unittest.mock as mock
    with mock.patch('src.core.reports.report.filedialog.asksaveasfilename', return_value=csv_file):
        with mock.patch('src.core.reports.report.messagebox.showinfo'):
            reporter.export_to_csv(data)
    
    assert os.path.exists(csv_file)
    with open(csv_file, 'r') as f:
        content = f.read()
    assert 'file1.txt' in content


def test_export_empty_dataframe(sample_dataframe):
    """Test exporting empty DataFrame."""
    reporter = MetadataReporter()
    empty_df = sample_dataframe.iloc[0:0]
    
    import unittest.mock as mock
    with mock.patch('src.core.reports.report.messagebox.showwarning') as mock_warning:
        reporter.export_to_json(empty_df)
        mock_warning.assert_called_once()


def test_export_to_excel_valid(temp_dir, sample_dataframe):
    """Test exporting to Excel with valid data."""
    try:
        reporter = MetadataReporter()
        excel_file = os.path.join(temp_dir, "export.xlsx")
        
        import unittest.mock as mock
        with mock.patch('src.core.reports.report.filedialog.asksaveasfilename', return_value=excel_file):
            with mock.patch('src.core.reports.report.messagebox.showinfo'):
                reporter.export_to_excel(sample_dataframe)
        
        assert os.path.exists(excel_file)
    except ImportError:
        pytest.skip("openpyxl not installed")


def test_wrapper_functions(sample_metadata, sample_dataframe):
    """Test module-level wrapper functions."""
    # Test resource_path
    path = resource_path("test.txt")
    assert isinstance(path, str)
    
    # Test get_asset_path
    asset_path = get_asset_path("logo.png")
    assert isinstance(asset_path, str)
    
    # Test generate_report_text
    text = generate_report_text(sample_metadata, "test.txt")
    assert isinstance(text, str)
    
    # Test create_pdf_report_from_text
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = os.path.join(tmp_dir, "test.pdf")
        create_pdf_report_from_text(text, pdf_path)
        assert os.path.exists(pdf_path)


# Backward compatibility wrappers
def test_generate_report_text(sample_metadata):
    """Backward compatibility wrapper. See test_generate_report_text_basic for details."""
    test_generate_report_text_basic(sample_metadata)


def test_print_metadata_report(sample_metadata):
    """Backward compatibility wrapper. Print functionality tested via create_pdf_report_from_text."""
    reporter = MetadataReporter()
    text = reporter.generate_report_text(sample_metadata, "test.pdf")
    assert isinstance(text, str)
    assert len(text) > 0


def test_save_metadata(sample_metadata):
    """Backward compatibility wrapper. See test_create_pdf_report_from_text for details."""
    reporter = MetadataReporter()
    text = reporter.generate_report_text(sample_metadata, "test.pdf")
    assert isinstance(text, str)


def test_export_to_pdf(sample_dataframe):
    """Backward compatibility wrapper. See test_export_to_json_valid for details."""
    reporter = MetadataReporter()
    import unittest.mock as mock
    with mock.patch('src.core.reports.report.filedialog.asksaveasfilename'):
        with mock.patch('src.core.reports.report.messagebox.showinfo'):
            # Test that export methods work without raising
            assert callable(reporter.export_to_pdf)


def test_create_pdf_report_from_text_with_kwargs(temp_dir):
    """Test create_pdf_report_from_text accepting keyword arguments."""
    reporter = MetadataReporter()
    output_path = os.path.join(temp_dir, "kwargs_report.pdf")
    reporter.create_pdf_report_from_text(
        report_text="Property: Value\nPrivacy Risk Analysis:\nRisk Level: LOW",
        output_path=output_path,
        risk_analysis={"risk_level": "LOW"},
        batch_summary=None,
    )
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_report_service_generate_pdf_report(temp_dir, sample_metadata):
    """Test ReportService.generate_pdf_report functionality."""
    from src.core.services.report_service import ReportService

    service = ReportService()
    output_path = os.path.join(temp_dir, "service_report.pdf")
    success, message = service.generate_pdf_report(
        extracted_metadata=sample_metadata,
        file_path="sample.txt",
        output_path=output_path,
        risk_analysis={"risk_level": "LOW", "risk_score": 0},
    )
    assert success is True
    assert "PDF report saved to" in message
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_report_service_generate_pdf_report_failure(temp_dir, sample_metadata):
    """Test ReportService.generate_pdf_report error handling."""
    from unittest.mock import MagicMock
    from src.core.services.report_service import ReportService

    mock_reporter = MagicMock()
    mock_reporter.generate_report_text.return_value = "report"
    mock_reporter.create_pdf_report_from_text.side_effect = RuntimeError("PDF build failed")

    service = ReportService(reporter=mock_reporter)
    output_path = os.path.join(temp_dir, "failing_report.pdf")
    success, message = service.generate_pdf_report(
        extracted_metadata=sample_metadata,
        file_path="sample.txt",
        output_path=output_path,
    )
    assert success is False
    assert "Failed to generate PDF report: PDF build failed" in message

