"""Unit tests for the BatchProcessDialog module."""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pytest
from src.gui.batch_process_dialog import (
    SUPPORTED_FILTER_PRESETS,
    BatchProcessDialog,
    format_file_size,
    open_batch_process_dialog,
)



def test_format_file_size():
    """Test byte formatting to clean human-readable size strings."""
    assert format_file_size(0) == "0 B"
    assert format_file_size(512) == "512 B"
    assert format_file_size(1024) == "1.0 KB"
    assert format_file_size(1536) == "1.5 KB"
    assert format_file_size(1024 * 1024) == "1.0 MB"
    assert format_file_size(5.5 * 1024 * 1024) == "5.5 MB"
    assert format_file_size(1024**3) == "1.0 GB"
    assert format_file_size(1024**4) == "1.0 TB"
    assert format_file_size(-100) == "0 B"
    assert format_file_size("invalid") == "0 B"
    assert format_file_size(None) == "0 B"


def test_supported_filter_presets():
    """Test that all filter presets exist and have appropriate file extensions."""
    assert "All Supported Formats" in SUPPORTED_FILTER_PRESETS
    assert "Documents (*.pdf, *.docx, *.txt, *.csv, *.xlsx)" in SUPPORTED_FILTER_PRESETS
    assert "Images (*.jpg, *.png, *.gif, *.bmp, *.webp, *.tiff)" in SUPPORTED_FILTER_PRESETS
    assert "Audio & Video (*.mp4, *.mp3, *.wav, *.avi, *.mkv)" in SUPPORTED_FILTER_PRESETS
    assert "Code & Scripts (*.py, *.js, *.html, *.css, *.json)" in SUPPORTED_FILTER_PRESETS
    assert "All Files (*.*)" in SUPPORTED_FILTER_PRESETS

    doc_exts = SUPPORTED_FILTER_PRESETS["Documents (*.pdf, *.docx, *.txt, *.csv, *.xlsx)"]
    assert ".pdf" in doc_exts
    assert ".docx" in doc_exts

    img_exts = SUPPORTED_FILTER_PRESETS["Images (*.jpg, *.png, *.gif, *.bmp, *.webp, *.tiff)"]
    assert ".jpg" in img_exts
    assert ".png" in img_exts


def test_batch_process_dialog_init():
    """Test initial attributes of BatchProcessDialog."""
    dialog = BatchProcessDialog(parent=None, app=None)
    assert dialog.parent is None
    assert dialog.app is None
    assert dialog.file_items == []
    assert dialog.path_set == set()
    assert dialog.is_processing is False
    assert dialog.stop_requested is False
    assert dialog.window is None


def test_ingest_paths_and_deduplication(tmp_path):
    """Test adding files with deduplication and metric tracking."""
    f1 = tmp_path / "doc1.pdf"
    f2 = tmp_path / "image1.png"
    f1.write_text("dummy pdf content")
    f2.write_text("dummy png content")

    dialog = BatchProcessDialog(parent=None, app=None)
    added = dialog._ingest_paths([str(f1), str(f2)])
    assert added == 2
    assert len(dialog.file_items) == 2
    assert len(dialog.path_set) == 2

    # Ingest duplicate paths
    added_dups = dialog._ingest_paths([str(f1), str(f2)])
    assert added_dups == 0
    assert len(dialog.file_items) == 2


def test_folder_scan_recursive_and_flat(tmp_path):
    """Test folder scanning both recursively and flat with extension filtering."""
    # Create directory tree
    sub_dir = tmp_path / "subfolder"
    sub_dir.mkdir()

    file_root_txt = tmp_path / "test1.txt"
    file_root_jpg = tmp_path / "photo.jpg"
    file_sub_pdf = sub_dir / "report.pdf"
    file_sub_bin = sub_dir / "binary.dat"

    file_root_txt.write_text("hello")
    file_root_jpg.write_text("image")
    file_sub_pdf.write_text("pdf document")
    file_sub_bin.write_text("data")

    # 1. Test Recursive Scan with All Supported Formats
    dialog_rec = BatchProcessDialog(parent=None, app=None)
    dialog_rec.recursive_var = mock.MagicMock()
    dialog_rec.recursive_var.get.return_value = True
    dialog_rec.filter_var = mock.MagicMock()
    dialog_rec.filter_var.get.return_value = "All Supported Formats"
    dialog_rec.status_var = mock.MagicMock()

    with mock.patch("tkinter.filedialog.askdirectory", return_value=str(tmp_path)):
        dialog_rec.add_folder()

    paths_rec = [item["path"] for item in dialog_rec.file_items]
    assert str(file_root_txt) in paths_rec
    assert str(file_root_jpg) in paths_rec
    assert str(file_sub_pdf) in paths_rec
    assert str(file_sub_bin) not in paths_rec  # .dat is not in supported filter

    # 2. Test Flat Scan (Non-recursive)
    dialog_flat = BatchProcessDialog(parent=None, app=None)
    dialog_flat.recursive_var = mock.MagicMock()
    dialog_flat.recursive_var.get.return_value = False
    dialog_flat.filter_var = mock.MagicMock()
    dialog_flat.filter_var.get.return_value = "All Supported Formats"
    dialog_flat.status_var = mock.MagicMock()

    with mock.patch("tkinter.filedialog.askdirectory", return_value=str(tmp_path)):
        dialog_flat.add_folder()

    paths_flat = [item["path"] for item in dialog_flat.file_items]
    assert str(file_root_txt) in paths_flat
    assert str(file_root_jpg) in paths_flat
    assert str(file_sub_pdf) not in paths_flat  # subfolder skipped in flat mode


def test_folder_scan_filter_preset(tmp_path):
    """Test folder scanning with specific filter preset (Images Only)."""
    f_img = tmp_path / "img1.png"
    f_doc = tmp_path / "doc1.docx"
    f_img.write_text("png")
    f_doc.write_text("docx")

    dialog = BatchProcessDialog(parent=None, app=None)
    dialog.recursive_var = mock.MagicMock()
    dialog.recursive_var.get.return_value = True
    dialog.filter_var = mock.MagicMock()
    dialog.filter_var.get.return_value = "Images (*.jpg, *.png, *.gif, *.bmp, *.webp, *.tiff)"
    dialog.status_var = mock.MagicMock()

    with mock.patch("tkinter.filedialog.askdirectory", return_value=str(tmp_path)):
        dialog.add_folder()

    paths = [item["path"] for item in dialog.file_items]
    assert str(f_img) in paths
    assert str(f_doc) not in paths


def test_clear_list_and_remove_selected(tmp_path):
    """Test removing selected items and clearing the queue."""
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("a")
    f2.write_text("b")

    dialog = BatchProcessDialog(parent=None, app=None)
    dialog._ingest_paths([str(f1), str(f2)])
    assert len(dialog.file_items) == 2

    # Clear list
    dialog.progress_var = mock.MagicMock()
    dialog.status_var = mock.MagicMock()
    dialog.clear_list()
    assert len(dialog.file_items) == 0
    assert len(dialog.path_set) == 0


def test_worker_thread_processing_success(tmp_path):
    """Test background batch worker with successful extraction and risk calculation."""
    f1 = tmp_path / "doc.txt"
    f1.write_text("test content")

    mock_app = mock.MagicMock()
    dialog = BatchProcessDialog(parent=None, app=mock_app)
    dialog._ingest_paths([str(f1)])

    mock_extractor = mock.MagicMock()
    mock_extractor.extract_and_store.return_value = ({"Line Count": 1, "Encoding": "utf-8"}, mock.MagicMock())

    mock_risk = mock.MagicMock()
    mock_risk.analyze_file.return_value = {
        "risk_level": "LOW",
        "risk_score": 10,
        "reasons": ["Clean text file"],
    }
    mock_risk.analyze_batch.return_value = {
        "risk_counts": {"LOW": 1, "MEDIUM": 0, "HIGH": 0},
        "total_files": 1,
    }

    with mock.patch("src.gui.batch_process_dialog.extractor", mock_extractor):
        with mock.patch("src.gui.batch_process_dialog.risk_analyzer", mock_risk):
            dialog._run_batch_worker()

    item = dialog.file_items[0]
    assert item["status"] == "Success"
    assert item["risk_level"] == "LOW"
    assert item["metadata"] == {"Line Count": 1, "Encoding": "utf-8"}


def test_worker_thread_processing_failure(tmp_path):
    """Test background batch worker with failed extraction handling."""
    f1 = tmp_path / "corrupted.dat"
    f1.write_text("bad data")

    dialog = BatchProcessDialog(parent=None, app=None)
    dialog._ingest_paths([str(f1)])

    mock_extractor = mock.MagicMock()
    mock_extractor.extract_and_store.return_value = ({"Error": "Corrupted or unsupported format"}, None)

    with mock.patch("src.gui.batch_process_dialog.extractor", mock_extractor):
        dialog._run_batch_worker()

    item = dialog.file_items[0]
    assert item["status"] == "Failed"
    assert item["metadata"] is None
    assert "Corrupted" in item["error"]


def test_worker_thread_stop_requested(tmp_path):
    """Test that stop_requested breaks out of the extraction loop."""
    f1 = tmp_path / "1.txt"
    f2 = tmp_path / "2.txt"
    f1.write_text("1")
    f2.write_text("2")

    dialog = BatchProcessDialog(parent=None, app=None)
    dialog._ingest_paths([str(f1), str(f2)])
    dialog.stop_requested = True

    dialog._run_batch_worker()
    # First item should not have been extracted because loop breaks
    assert dialog.file_items[0]["status"] == "Pending"
    assert dialog.file_items[1]["status"] == "Pending"


def test_export_results_to_csv_and_json(tmp_path):
    """Test exporting batch results to CSV and JSON formats."""
    f1 = tmp_path / "test.txt"
    f1.write_text("hello")

    dialog = BatchProcessDialog(parent=None, app=None)
    dialog._ingest_paths([str(f1)])
    dialog.file_items[0]["status"] = "Success"
    dialog.file_items[0]["risk_level"] = "LOW"
    dialog.file_items[0]["risk_score"] = 5
    dialog.file_items[0]["metadata"] = {"Encoding": "utf-8"}

    csv_target = str(tmp_path / "export.csv")
    json_target = str(tmp_path / "export.json")

    # Test CSV export
    with mock.patch("tkinter.filedialog.asksaveasfilename", return_value=csv_target):
        with mock.patch("tkinter.messagebox.showinfo"):
            dialog.export_results()

    assert os.path.exists(csv_target)
    with open(csv_target, "r", encoding="utf-8") as f:
        content = f.read()
        assert "test.txt" in content
        assert "Success" in content
        assert "LOW" in content

    # Test JSON export
    with mock.patch("tkinter.filedialog.asksaveasfilename", return_value=json_target):
        with mock.patch("tkinter.messagebox.showinfo"):
            dialog.export_results()

    assert os.path.exists(json_target)
    with open(json_target, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["file_name"] == "test.txt"
        assert data[0]["status"] == "Success"
        assert data[0]["risk_level"] == "LOW"


def test_open_batch_process_dialog_wrapper():
    """Test open_batch_process_dialog wrapper function."""
    with mock.patch.object(BatchProcessDialog, "show") as mock_show:
        dialog = open_batch_process_dialog(parent=None)
        assert isinstance(dialog, BatchProcessDialog)
        mock_show.assert_called_once()


def test_start_processing_button_states(tmp_path):
    """Test that start_processing updates both toolbar and bottom buttons."""
    f1 = tmp_path / "test.txt"
    f1.write_text("content")

    dialog = BatchProcessDialog(parent=None, app=None)
    dialog._ingest_paths([str(f1)])

    dialog.btn_start = mock.MagicMock()
    dialog.btn_tb_start = mock.MagicMock()
    dialog.btn_stop = mock.MagicMock()
    dialog.btn_tb_stop = mock.MagicMock()
    dialog.progress_var = mock.MagicMock()
    dialog.status_var = mock.MagicMock()

    with mock.patch("threading.Thread") as mock_thread_cls:
        dialog.start_processing()
        dialog.btn_start.config.assert_called_with(state="disabled")
        dialog.btn_tb_start.config.assert_called_with(state="disabled")
        dialog.btn_stop.config.assert_called_with(state="normal")
        dialog.btn_tb_stop.config.assert_called_with(state="normal")

