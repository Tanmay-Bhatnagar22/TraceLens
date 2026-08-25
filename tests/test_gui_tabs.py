import sys
from pathlib import Path
import unittest.mock as mock
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from gui import (
    MetadataAnalyzerApp,
    ExtractorTab,
    EditorTab,
    HistoryTab,
    RiskTab,
    PreviewTab,
)


@pytest.fixture
def app():
    """Create application instance for testing."""
    return MetadataAnalyzerApp()


def test_tab_imports():
    """Test that all tab classes can be imported from src.gui and src.gui.tabs."""
    from src.gui.tabs import ExtractorTab, EditorTab, HistoryTab, RiskTab, PreviewTab
    assert ExtractorTab is not None
    assert EditorTab is not None
    assert HistoryTab is not None
    assert RiskTab is not None
    assert PreviewTab is not None


def test_editor_tab_non_editable_fields():
    """Test that EditorTab defines NON_EDITABLE_FIELDS."""
    assert hasattr(EditorTab, "NON_EDITABLE_FIELDS")
    assert "File Name" in EditorTab.NON_EDITABLE_FIELDS
    assert "File Size" in EditorTab.NON_EDITABLE_FIELDS
    assert "File Type" in EditorTab.NON_EDITABLE_FIELDS
    assert "Extracted At" in EditorTab.NON_EDITABLE_FIELDS
    assert "Modified On" in EditorTab.NON_EDITABLE_FIELDS


def test_editor_tab_is_editable():
    """Test EditorTab is_editable_field method."""
    mock_frame = mock.MagicMock()
    mock_app = mock.MagicMock()
    with mock.patch.object(EditorTab, "build_ui"):
        tab = EditorTab(mock_frame, mock_app)
        assert tab.is_editable_field("Author") is True
        assert tab.is_editable_field("File Name") is False


def test_extractor_tab_welcome_text(app):
    """Test ExtractorTab show_welcome_text."""
    mock_frame = mock.MagicMock()
    with mock.patch.object(ExtractorTab, "build_ui"):
        tab = ExtractorTab(mock_frame, app)
        mock_text = mock.MagicMock()
        app.c1_text = mock_text
        tab.show_welcome_text()
        mock_text.config.assert_called()
        mock_text.delete.assert_called_with(1.0, "end")
        mock_text.insert.assert_called()


def test_preview_tab_zoom_controls(app):
    """Test PreviewTab zoom in, zoom out, and reset zoom."""
    mock_frame = mock.MagicMock()
    with mock.patch.object(PreviewTab, "build_ui"), mock.patch.object(PreviewTab, "apply_image_zoom"):
        tab = PreviewTab(mock_frame, app)
        app.preview_base_image = mock.MagicMock()
        app.preview_image_zoom = 1.0

        tab.zoom_in_image()
        assert app.preview_image_zoom == pytest.approx(1.2)

        tab.zoom_out_image()
        assert app.preview_image_zoom == pytest.approx(1.0)

        tab.zoom_out_image()
        assert app.preview_image_zoom == pytest.approx(0.8)

        tab.reset_zoom_image()
        assert app.preview_image_zoom == pytest.approx(1.0)


def test_history_tab_clear_filters(app):
    """Test HistoryTab clear_filters."""
    mock_frame = mock.MagicMock()
    with mock.patch.object(HistoryTab, "build_ui"), mock.patch.object(HistoryTab, "load_data"):
        tab = HistoryTab(mock_frame, app)
        tab.search_var = mock.MagicMock()
        tab.filter_var = mock.MagicMock()
        tab.date_var = mock.MagicMock()
        tab.sort_var = mock.MagicMock()
        tab.search_entry = mock.MagicMock()

        tab.clear_filters()

        tab.search_var.set.assert_called_with("")
        tab.filter_var.set.assert_called_with("All")
        tab.date_var.set.assert_called_with("All Time")
        tab.sort_var.set.assert_called_with("Date (Newest)")
        tab.search_entry.focus_set.assert_called_once()


def test_history_tab_on_tree_double_click(app):
    """Test HistoryTab on_tree_double_click loads record into Extractor without NameError."""
    import json
    import src.gui.tabs.history_tab as history_tab_mod
    mock_frame = mock.MagicMock()
    with mock.patch.object(HistoryTab, "build_ui"), mock.patch.object(HistoryTab, "load_data"):
        tab = HistoryTab(mock_frame, app)
        mock_tree = mock.MagicMock()
        mock_tree.selection.return_value = ["item1"]
        mock_tree.item.return_value = {
            "values": (1, "/path/to/test_sample.jpg", "test_sample.jpg", "100 KB", "image", "LOW", "2026-08-25", "2026-08-25", 42)
        }
        tab.tree = mock_tree

        fake_row = (42, "/path/to/test_sample.jpg", "test_sample.jpg", "100 KB", "image", "2026-08-25T12:00:00", "2026-08-25T12:00:00", json.dumps({"Make": "Canon"}))
        with mock.patch.object(history_tab_mod.db, "fetch_metadata_by_id", return_value=fake_row):
            app.c1_text = mock.MagicMock()
            app.nb_widget = mock.MagicMock()
            app.nb_widget.tabs.return_value = ["tab1", "tab2"]

            # Trigger double click
            tab.on_tree_double_click(mock.MagicMock())

            assert app.file_path == "/path/to/test_sample.jpg"
            assert app.extracted_metadata == {"Make": "Canon"}
            app.nb_widget.select.assert_called_with("tab1")
            app.c1_text.insert.assert_called()


def test_risk_tab_open_risk_analyzer_with_scan(app):
    """Test RiskTab open_risk_analyzer_with_scan runs without NameError."""
    import src.gui.tabs.risk_tab as risk_tab_mod
    mock_frame = mock.MagicMock()
    with mock.patch.object(RiskTab, "build_ui"), mock.patch.object(RiskTab, "render_risk_analysis"):
        tab = RiskTab(mock_frame, app)
        app.file_path = "/path/to/test_image.png"
        app.extracted_metadata = {"Author": "Alice"}
        app.nb_widget = mock.MagicMock()
        app.tab5_ref = "tab5"

        with mock.patch.object(risk_tab_mod.risk_analyzer, "analyze_metadata", return_value={"risk_score": 10, "risk_level": "LOW"}) as mock_analyze:
            tab.open_risk_analyzer_with_scan()
            mock_analyze.assert_called_once()
            app.nb_widget.select.assert_called_with("tab5")


