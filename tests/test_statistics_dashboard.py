"""Unit tests for the Statistical Dashboard module."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / 'src'
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pytest
from src.gui.gui import MetadataAnalyzerApp
from src.gui.statistics_dashboard import (
    StatisticsDashboard,
    calculate_enhanced_stats,
    create_metric_card,
    filter_records,
    format_size,
    open_statistics_dashboard,
    parse_size_to_bytes,
)


def test_parse_size_to_bytes():
    """Test size parsing from human-readable strings and numbers to bytes."""
    assert parse_size_to_bytes("100 B") == 100
    assert parse_size_to_bytes("1 KB") == 1024
    assert parse_size_to_bytes("2.5 MB") == int(2.5 * 1024 * 1024)
    assert parse_size_to_bytes("1 GB") == 1024**3
    assert parse_size_to_bytes("1 TB") == 1024**4
    assert parse_size_to_bytes(5000) == 5000
    assert parse_size_to_bytes("5000") == 5000
    assert parse_size_to_bytes(None) == 0
    assert parse_size_to_bytes("") == 0
    assert parse_size_to_bytes("Unknown") == 0
    assert parse_size_to_bytes("invalid data") == 0


def test_format_size():
    """Test byte formatting to human-readable size strings."""
    assert format_size(0) == "0.0 B"
    assert format_size(512) == "512.0 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
    assert format_size(1024**3) == "1.0 GB"
    assert format_size(1024**4) == "1.0 TB"
    assert format_size("invalid") == "0.0 B"


def test_filter_records_date_and_type_and_search():
    """Test record filtering across date ranges, file types, and search queries."""
    now = datetime.now()
    records = [
        # (id, path, filename, size, file_type, extracted_at, modified_on, metadata_json)
        (1, "/tmp/doc1.pdf", "doc1.pdf", "1.5 MB", "PDF", (now - timedelta(days=2)).isoformat(), now.isoformat(), "{}"),
        (2, "/tmp/img1.png", "img1.png", "500 KB", "PNG", (now - timedelta(days=15)).isoformat(), now.isoformat(), "{}"),
        (3, "/tmp/doc2.pdf", "doc2.pdf", "2.0 MB", "PDF", (now - timedelta(days=60)).isoformat(), now.isoformat(), "{}"),
        (4, "/tmp/report.docx", "report.docx", "300 KB", "DOCX", (now - timedelta(days=120)).isoformat(), now.isoformat(), "{}"),
    ]

    # All time
    assert len(filter_records(records, {'date_range': 'All Time'})) == 4

    # Last 7 Days
    last_7 = filter_records(records, {'date_range': 'Last 7 Days'})
    assert len(last_7) == 1
    assert last_7[0][2] == "doc1.pdf"

    # Last 30 Days
    last_30 = filter_records(records, {'date_range': 'Last 30 Days'})
    assert len(last_30) == 2

    # Last 90 Days
    last_90 = filter_records(records, {'date_range': 'Last 90 Days'})
    assert len(last_90) == 3

    # File type filter
    pdf_only = filter_records(records, {'file_type': 'PDF'})
    assert len(pdf_only) == 2
    assert all(r[4] == 'PDF' for r in pdf_only)

    # Search filter
    search_img = filter_records(records, {'search': 'img1'})
    assert len(search_img) == 1
    assert search_img[0][2] == "img1.png"

    search_case_insensitive = filter_records(records, {'search': 'DOC'})
    assert len(search_case_insensitive) == 3  # doc1.pdf, doc2.pdf, and report.docx


def test_calculate_enhanced_stats_empty():
    """Test calculate_enhanced_stats with an empty record list."""
    assert calculate_enhanced_stats([]) is None


def test_calculate_enhanced_stats_populated():
    """Test calculate_enhanced_stats calculation logic and risk integration."""
    now = datetime.now()
    records = [
        (1, "/tmp/a.pdf", "a.pdf", "1000 B", "PDF", now.isoformat(), now.isoformat(), '{"Author": "Alice"}'),
        (2, "/tmp/b.png", "b.png", "2000 B", "PNG", now.isoformat(), now.isoformat(), '{"GPS": "12,34"}'),
        (3, "/tmp/c.pdf", "c.pdf", "3000 B", "PDF", now.isoformat(), now.isoformat(), '{}'),
    ]

    mock_risk = mock.MagicMock()
    mock_risk.analyze_metadata.side_effect = [
        {'risk_level': 'LOW'},
        {'risk_level': 'HIGH'},
        {'risk_level': 'MEDIUM'},
    ]

    stats = calculate_enhanced_stats(records, risk_analyzer_module=mock_risk)

    assert stats is not None
    assert stats['total'] == 3
    assert stats['total_size'] == 6000
    assert stats['avg_size'] == 2000
    assert stats['file_types']['PDF'] == 2
    assert stats['file_types']['PNG'] == 1
    assert stats['max_size'][0] == 3000
    assert stats['min_size'][0] == 1000
    assert stats['risk_counts']['HIGH'] == 1
    assert stats['risk_counts']['MEDIUM'] == 1
    assert stats['risk_counts']['LOW'] == 1
    assert len(stats['largest_files']) == 3


def test_statistics_dashboard_initialization():
    """Test StatisticsDashboard instance creation and default attributes."""
    mock_db = mock.MagicMock()
    dashboard = StatisticsDashboard(database=mock_db)

    assert dashboard.parent is None
    assert dashboard.db == mock_db
    assert dashboard.window is None
    assert 'records_cache' in dashboard.dashboard_state
    assert dashboard.dashboard_state['request_token'] == 0


def test_create_metric_card_headless():
    """Test create_metric_card frame creation."""
    mock_parent = mock.MagicMock()
    with mock.patch('src.gui.statistics_dashboard.Frame') as mock_frame, \
         mock.patch('src.gui.statistics_dashboard.Label') as mock_label:
        card = create_metric_card(mock_parent, "Test Metric", "123", subtitle="Sub")
        assert card is not None
        mock_frame.assert_called()
        mock_label.assert_called()


def test_app_delegation_to_statistics_module():
    """Test that MetadataAnalyzerApp methods properly delegate to the statistics dashboard module."""
    app = MetadataAnalyzerApp()
    
    with mock.patch('src.gui.gui.create_metric_card') as mock_create_card:
        parent_mock = mock.MagicMock()
        app._create_metric_card(parent_mock, "Files", "10", "Analyzed")
        mock_create_card.assert_called_once_with(parent_mock, "Files", "10", "Analyzed", "#667eea", "#764ba2", None)

    with mock.patch('src.gui.gui.open_statistics_dashboard') as mock_open_stats:
        app.menu_statistics()
        mock_open_stats.assert_called_once_with(app.root)


def test_forensic_insights_calculation():
    """Test forensic metrics, completeness score, duplicate detection, and executive summary."""
    now = datetime.now()
    records = [
        (1, "/tmp/doc1.pdf", "report.pdf", "1.5 MB", "PDF", now.isoformat(), now.isoformat(), '{"Author": "Alice", "Software": "Acrobat", "GPS": "1,2"}'),
        (2, "/tmp/doc2.pdf", "report.pdf", "1.5 MB", "PDF", now.isoformat(), now.isoformat(), '{"Author": "Alice", "Software": "Acrobat"}'),
        (3, "/tmp/img.png", "photo.png", "3.0 MB", "PNG", now.isoformat(), now.isoformat(), '{"Software": "Photoshop"}'),
    ]

    stats = calculate_enhanced_stats(records)
    assert stats is not None
    assert stats["total"] == 3
    assert len(stats["duplicates"]) == 1
    assert stats["duplicates"][0]["filename"] == "report.pdf"
    assert stats["duplicates"][0]["count"] == 2
    assert stats["authors"]["Alice"] == 2
    assert stats["software"]["Acrobat"] == 2
    assert stats["software"]["Photoshop"] == 1
    assert stats["avg_completeness"] > 0
    assert "TraceLens indexed 3 file records" in stats["executive_summary"]


def test_filter_records_today_and_presets():
    """Test filtering records with 'Today' and 'This Year' presets."""
    now = datetime.now()
    records = [
        (1, "/tmp/a.pdf", "a.pdf", "100 B", "PDF", now.isoformat(), now.isoformat(), "{}"),
        (2, "/tmp/b.pdf", "b.pdf", "200 B", "PDF", (now - timedelta(days=2)).isoformat(), now.isoformat(), "{}"),
    ]

    today_records = filter_records(records, {"date_range": "Today"})
    assert len(today_records) == 1
    assert today_records[0][0] == 1

    year_records = filter_records(records, {"date_range": "This Year"})
    assert len(year_records) >= 1


def test_dashboard_tabs_structure():
    """Test StatisticsDashboard tabs structure without data explorer."""
    dashboard = StatisticsDashboard()
    assert not hasattr(dashboard, "tab_explorer")
    assert "records_cache" in dashboard.dashboard_state
    assert dashboard.dashboard_state["request_token"] == 0


def test_history_tab_risk_column():
    """Test that HistoryTab properly configures Risk column in treeview."""
    from src.gui.tabs.history_tab import HistoryTab
    app_mock = mock.MagicMock()
    parent_mock = mock.MagicMock()
    with mock.patch("src.gui.tabs.history_tab.Frame"), \
         mock.patch("src.gui.tabs.history_tab.ttk.Treeview") as mock_tree_cls, \
         mock.patch.object(HistoryTab, "load_data"):
        tab = HistoryTab(parent_mock, app_mock)
        assert tab is not None
        mock_tree_cls.assert_called_once()
        # Verify columns argument includes 'Risk'
        call_kwargs = mock_tree_cls.call_args[1]
        assert "Risk" in call_kwargs.get("columns", ())


