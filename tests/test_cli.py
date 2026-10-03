import sys
from pathlib import Path
import types
import subprocess
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import cli


def test_normalize_path_strips_quotes_and_whitespace():
    raw = '  "C:/tmp/sample.txt"  '
    assert cli._normalize_path(raw).endswith("sample.txt")


def test_prompt_path_retries_until_non_empty(monkeypatch, capsys):
    responses = iter(["", "   ", " ./data.txt "])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    result = cli.prompt_path("Enter file path")
    out = capsys.readouterr().out

    assert result.endswith("data.txt")
    assert "Path cannot be empty." in out


def test_quick_extract_success(monkeypatch, capsys):
    monkeypatch.setattr(cli, "prompt_path", lambda _text: "file.txt")
    monkeypatch.setattr(cli.extractor, "extract_and_store", lambda _path: ({"Title": "Doc"}, None))

    called = {"value": False}

    def fake_pretty(meta):
        called["value"] = True
        assert meta["Title"] == "Doc"

    monkeypatch.setattr(cli, "pretty_print_metadata", fake_pretty)

    cli.quick_extract()
    out = capsys.readouterr().out

    assert "Metadata extracted and saved to database." in out
    assert called["value"] is True


def test_quick_extract_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "prompt_path", lambda _text: "missing.txt")
    monkeypatch.setattr(cli.extractor, "extract_and_store", lambda _path: ({"Error": "Bad file"}, None))

    cli.quick_extract()
    out = capsys.readouterr().out

    assert "Error: Bad file" in out


def test_analyze_single_file_risk_success(monkeypatch, capsys):
    monkeypatch.setattr(cli, "prompt_path", lambda _text: "file.txt")
    monkeypatch.setattr(cli.extractor, "extract", lambda _path: {"Author": "A"})
    monkeypatch.setattr(
        cli.risk_analyzer,
        "analyze_metadata",
        lambda _meta, _path: {
            "file_name": "file.txt",
            "risk_score": 75,
            "risk_level": "HIGH",
            "reasons": ["Author metadata present"],
            "timeline": [{"event": "Created", "timestamp": "2025-01-01"}],
        },
    )

    cli.analyze_single_file_risk()
    out = capsys.readouterr().out

    assert "Risk Score: 75/100" in out
    assert "Risk Level: HIGH" in out
    assert "Author metadata present" in out
    assert "Created: 2025-01-01" in out


def test_generate_report_cli_saves_txt_and_pdf(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "prompt_path", lambda _text: "C:/tmp/input_file.txt")
    monkeypatch.setattr(cli.extractor, "extract", lambda _path: {"Title": "Doc"})
    monkeypatch.setattr(cli.risk_analyzer, "analyze_metadata", lambda _meta, _path: {"risk_score": 10})
    monkeypatch.setattr(cli.report, "generate_report_text", lambda *_args, **_kwargs: "report body")

    pdf_calls = []
    monkeypatch.setattr(cli.report, "create_pdf_report_from_text", lambda text, out: pdf_calls.append((text, out)))
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)

    class _FakeNow:
        def strftime(self, _fmt):
            return "20260101_000000"

    fake_datetime = types.SimpleNamespace(now=lambda: _FakeNow())
    monkeypatch.setattr(cli, "datetime", fake_datetime)
    monkeypatch.setattr("builtins.input", lambda _prompt: "both")

    cli.generate_report_cli()
    out = capsys.readouterr().out

    txt_path = tmp_path / "input_file_report_20260101_000000.txt"
    pdf_path = tmp_path / "input_file_report_20260101_000000.pdf"

    assert txt_path.exists()
    assert txt_path.read_text(encoding="utf-8") == "report body"
    assert pdf_calls == [("report body", str(pdf_path))]
    assert "TXT saved:" in out
    assert "PDF saved:" in out


def test_generate_report_cli_unknown_option(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "prompt_path", lambda _text: "C:/tmp/input_file.txt")
    monkeypatch.setattr(cli.extractor, "extract", lambda _path: {"Title": "Doc"})
    monkeypatch.setattr(cli.risk_analyzer, "analyze_metadata", lambda _meta, _path: {"risk_score": 10})
    monkeypatch.setattr(cli.report, "generate_report_text", lambda *_args, **_kwargs: "report body")
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "weird")

    pdf_calls = []
    monkeypatch.setattr(cli.report, "create_pdf_report_from_text", lambda *_args: pdf_calls.append(True))

    cli.generate_report_cli()
    out = capsys.readouterr().out

    assert not list(tmp_path.glob("*.txt"))
    assert pdf_calls == []
    assert "Unknown option. Nothing saved." in out


def test_iter_files_returns_nested_files(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("b", encoding="utf-8")

    files = cli._iter_files(tmp_path)
    names = {path.name for path in files}

    assert names == {"a.txt", "b.txt"}


def test_batch_scan_folder_reports_summary(monkeypatch, tmp_path, capsys):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("a", encoding="utf-8")
    file_b.write_text("b", encoding="utf-8")

    monkeypatch.setattr(cli, "prompt_path", lambda _text: str(tmp_path))

    responses = iter([{"Title": "ok"}, {"Error": "failed"}])
    monkeypatch.setattr(cli.extractor, "extract", lambda _path: next(responses))

    insert_calls = []
    monkeypatch.setattr(cli.db, "insert_metadata", lambda path, metadata: insert_calls.append((path, metadata)))
    monkeypatch.setattr(
        cli.risk_analyzer,
        "analyze_batch",
        lambda entries: {
            "total_files": len(entries),
            "risk_counts": {"LOW": 1, "MEDIUM": 0, "HIGH": 0},
        },
    )

    cli.batch_scan_folder()
    out = capsys.readouterr().out

    assert len(insert_calls) == 1
    assert "Successful: 1" in out
    assert "Failed: 1" in out
    assert "LOW: 1" in out


def test_view_recent_history_handles_invalid_limit(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _prompt: "abc")
    monkeypatch.setattr(cli.db, "get_recent_records", lambda limit=10: [])

    cli.view_recent_history()
    out = capsys.readouterr().out

    assert "Invalid number. Showing 10 records." in out
    assert "No history records found." in out


def test_launch_gui_calls_main(monkeypatch):
    called = {"value": 0}
    monkeypatch.setattr(cli, "_run_gui_main", lambda: called.__setitem__("value", called["value"] + 1))

    cli.launch_gui()

    assert called["value"] == 1


def test_launch_gui_missing_dependency(monkeypatch, capsys):
    def _raise_missing():
        raise ModuleNotFoundError("No module named 'matplotlib'", name="matplotlib")

    monkeypatch.setattr(cli, "_run_gui_main", _raise_missing)

    cli.launch_gui()
    out = capsys.readouterr().out

    assert "GUI dependency missing: matplotlib" in out
    assert "pip install -r requirements.txt" in out


def test_launch_gui_uses_project_venv_on_missing_dependency(monkeypatch, tmp_path, capsys):
    def _raise_missing():
        raise ModuleNotFoundError("No module named 'matplotlib'", name="matplotlib")

    monkeypatch.setattr(cli, "_run_gui_main", _raise_missing)

    fake_python = tmp_path / "python.exe"
    fake_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(cli, "_project_venv_python", lambda: fake_python)

    popen_calls = []

    class _DummyProcess:
        pass

    def _fake_popen(cmd, cwd=None):
        popen_calls.append((cmd, cwd))
        return _DummyProcess()

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)

    cli.launch_gui()
    out = capsys.readouterr().out

    assert len(popen_calls) == 1
    assert str(fake_python) in popen_calls[0][0][0]
    assert "GUI launched using project venv" in out


def test_run_cli_help_then_exit(monkeypatch):
    monkeypatch.setattr(cli, "clear_screen", lambda: None)
    monkeypatch.setattr(cli, "banner", lambda: None)
    monkeypatch.setattr(cli, "print_menu", lambda: None)
    monkeypatch.setattr(cli, "_enable_ansi_windows", lambda: None)

    called = {"help": 0}
    monkeypatch.setattr(cli, "help_text", lambda: called.__setitem__("help", called["help"] + 1))

    responses = iter(["help", "", "0"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    cli.run_cli()

    assert called["help"] == 1


# ==============================================================================
# Service Layer Integration Tests for CLI
# ==============================================================================

import json
from typer.testing import CliRunner
from src.core.services import ServiceContainer, reset_service_container
from src.models import ExtractionResult, RiskAssessment, BatchExtractionResult, BatchRiskResult


@pytest.fixture(autouse=True)
def reset_services_fixture():
    """Ensure clean service container state for each test."""
    reset_service_container()
    cli.set_services(None)
    yield
    reset_service_container()
    cli.set_services(None)


def test_cli_get_services_returns_container():
    """Verify get_services returns a valid ServiceContainer instance."""
    container = cli.get_services()
    assert isinstance(container, ServiceContainer)
    assert container.extraction is not None
    assert container.risk is not None
    assert container.editor is not None
    assert container.history is not None
    assert container.report is not None
    assert container.analytics is not None


def test_cli_set_services_injection():
    """Verify programmatic injection of custom ServiceContainer."""
    custom_container = ServiceContainer()
    cli.set_services(custom_container)
    assert cli.get_services() is custom_container


def test_cli_extract_single_file_command(tmp_path):
    """Test 'tracelens extract' on a single file using the service layer."""
    runner = CliRunner()
    test_file = tmp_path / "document.txt"
    test_file.write_text("Hello TraceLens", encoding="utf-8")
    db_file = tmp_path / "test.db"

    result = runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])
    assert result.exit_code == 0
    assert "Metadata for document.txt" in result.output
    assert "Extraction Complete" in result.output
    assert "Saved to database: yes" in result.output


def test_cli_extract_no_save_option(tmp_path):
    """Test 'tracelens extract --no-save' skips DB persistence."""
    runner = CliRunner()
    test_file = tmp_path / "photo.txt"
    test_file.write_text("dummy photo metadata", encoding="utf-8")
    db_file = tmp_path / "test.db"

    result = runner.invoke(cli.app, ["--db-path", str(db_file), "extract", "--no-save", str(test_file)])
    assert result.exit_code == 0
    assert "Saved to database: no" in result.output


def test_cli_extract_batch_command(tmp_path):
    """Test 'tracelens extract --recursive' across multiple files in a directory."""
    runner = CliRunner()
    folder = tmp_path / "batch_files"
    folder.mkdir()
    (folder / "f1.txt").write_text("a", encoding="utf-8")
    (folder / "f2.txt").write_text("b", encoding="utf-8")
    db_file = tmp_path / "test.db"

    result = runner.invoke(cli.app, ["--db-path", str(db_file), "extract", "--recursive", str(folder)])
    assert result.exit_code == 0
    assert "Batch Extraction Summary" in result.output
    assert "Successful: 2" in result.output


def test_cli_extract_missing_file_fails():
    """Test 'tracelens extract' with non-existent file returns FILE_ERROR exit code (3)."""
    runner = CliRunner()
    result = runner.invoke(cli.app, ["extract", "non_existent_file_99999.pdf"])
    assert result.exit_code == cli.EXIT_FILE_ERROR
    assert "File not found: non_existent_file_99999.pdf" in result.output
    assert "Use 'tracelens extract --help' for usage information." in result.output


def test_cli_analyze_single_file_command(tmp_path):
    """Test 'tracelens analyze' on a single file with risk scoring and suggestions."""
    runner = CliRunner()
    test_file = tmp_path / "sample.txt"
    test_file.write_text("sample content", encoding="utf-8")

    result = runner.invoke(cli.app, ["analyze", str(test_file)])
    assert result.exit_code == 0
    assert "Risk Analysis" in result.output
    assert "Risk Score:" in result.output
    assert "Analysis Complete" in result.output


def test_cli_analyze_batch_command(tmp_path):
    """Test 'tracelens analyze' across multiple files."""
    runner = CliRunner()
    (tmp_path / "f1.txt").write_text("a", encoding="utf-8")
    (tmp_path / "f2.txt").write_text("b", encoding="utf-8")

    result = runner.invoke(cli.app, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
    assert "Batch Analysis Summary" in result.output
    assert "Files analyzed: 2" in result.output


def test_cli_sanitize_command_creates_backup(tmp_path):
    """Test 'tracelens sanitize' command strips sensitive tags and creates .bak."""
    runner = CliRunner()
    test_file = tmp_path / "sanitizeme.txt"
    test_file.write_text("Confidential metadata", encoding="utf-8")

    result = runner.invoke(cli.app, ["sanitize", str(test_file), "--backup"])
    assert result.exit_code == 0
    assert "Sanitization Summary" in result.output
    assert "Successfully sanitized: 1" in result.output
    assert (tmp_path / "sanitizeme.txt.bak").exists()


def test_cli_sanitize_no_backup(tmp_path):
    """Test 'tracelens sanitize --no-backup' doesn't create backup."""
    runner = CliRunner()
    test_file = tmp_path / "cleanme.txt"
    test_file.write_text("Metadata to scrub", encoding="utf-8")

    result = runner.invoke(cli.app, ["sanitize", str(test_file), "--no-backup"])
    assert result.exit_code == 0
    assert "Sanitization Summary" in result.output
    assert "Successfully sanitized: 1" in result.output
    assert not (tmp_path / "cleanme.txt.bak").exists()


def test_cli_edit_command(tmp_path):
    """Test 'tracelens edit' modifying metadata via --set."""
    runner = CliRunner()
    test_file = tmp_path / "editable.txt"
    test_file.write_text("Editable content", encoding="utf-8")
    db_file = tmp_path / "test.db"

    # First extract so it's in db
    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

    # Now edit
    result = runner.invoke(
        cli.app,
        ["--db-path", str(db_file), "edit", str(test_file), "--set", "Author=TestAuthor"],
    )
    assert result.exit_code == 0
    assert "Metadata Edit" in result.output
    assert "Author: TestAuthor" in result.output
    assert "Persistence" in result.output


def test_cli_report_command(tmp_path):
    """Test 'tracelens report' generating reports."""
    runner = CliRunner()
    test_file = tmp_path / "reportable.txt"
    test_file.write_text("Reportable data", encoding="utf-8")
    out_dir = tmp_path / "reports_out"

    result = runner.invoke(
        cli.app,
        ["report", str(test_file), "--format", "txt", "--output-dir", str(out_dir)],
    )
    assert result.exit_code == 0
    assert "Report Preview" in result.output
    assert "Saved Reports" in result.output
    assert len(list(out_dir.glob("*.txt"))) == 1


def test_cli_report_command_pdf_and_both(tmp_path):
    """Test 'tracelens report' generating pdf and both format reports."""
    runner = CliRunner()
    test_file = tmp_path / "reportable_pdf.txt"
    test_file.write_text("Reportable data for pdf", encoding="utf-8")
    out_dir_pdf = tmp_path / "reports_out_pdf"
    out_dir_both = tmp_path / "reports_out_both"

    result_pdf = runner.invoke(
        cli.app,
        ["report", str(test_file), "--format", "pdf", "--output-dir", str(out_dir_pdf)],
    )
    assert result_pdf.exit_code == 0
    assert len(list(out_dir_pdf.glob("*.pdf"))) == 1
    assert len(list(out_dir_pdf.glob("*.txt"))) == 0

    result_both = runner.invoke(
        cli.app,
        ["report", str(test_file), "--format", "both", "--output-dir", str(out_dir_both)],
    )
    assert result_both.exit_code == 0
    assert len(list(out_dir_both.glob("*.pdf"))) == 1
    assert len(list(out_dir_both.glob("*.txt"))) == 1


def test_cli_export_command_json(tmp_path):
    """Test 'tracelens export' exporting records to JSON."""
    runner = CliRunner()
    db_file = tmp_path / "test.db"
    test_file = tmp_path / "export_file.txt"
    test_file.write_text("content", encoding="utf-8")

    # Extract to populate DB
    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

    export_json = tmp_path / "out.json"
    result = runner.invoke(
        cli.app,
        ["--db-path", str(db_file), "export", "json", "--output", str(export_json)],
    )
    assert result.exit_code == 0
    assert "Export Complete" in result.output
    assert export_json.exists()


def test_cli_history_subcommands(tmp_path):
    """Test 'tracelens history', 'history stats', 'history delete', and 'history clear'."""
    runner = CliRunner()
    db_file = tmp_path / "test.db"
    test_file = tmp_path / "hist.txt"
    test_file.write_text("content", encoding="utf-8")

    # Extract to populate DB
    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

    # View history
    res_hist = runner.invoke(cli.app, ["--db-path", str(db_file), "history"])
    assert res_hist.exit_code == 0
    assert "Recent History" in res_hist.output
    assert "hist.txt" in res_hist.output

    # View stats
    res_stats = runner.invoke(cli.app, ["--db-path", str(db_file), "history", "stats"])
    assert res_stats.exit_code == 0
    assert "Database Statistics" in res_stats.output
    assert "Total Records: 1" in res_stats.output

    # Delete record
    res_del = runner.invoke(cli.app, ["--db-path", str(db_file), "history", "delete", "1", "--yes"])
    assert res_del.exit_code == 0
    assert "History Updated" in res_del.output

    # Clear history
    res_clear = runner.invoke(cli.app, ["--db-path", str(db_file), "history", "clear", "--yes"])
    assert res_clear.exit_code == 0
    assert "History Cleared" in res_clear.output


def test_cli_analytics_and_stats_commands(tmp_path):
    """Test 'tracelens analytics' and 'tracelens stats' commands."""
    runner = CliRunner()
    db_file = tmp_path / "test.db"
    test_file = tmp_path / "analytics.txt"
    test_file.write_text("some content for stats", encoding="utf-8")

    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

    # Test analytics command
    res_analytics = runner.invoke(cli.app, ["--db-path", str(db_file), "analytics"])
    assert res_analytics.exit_code == 0
    assert "TraceLens Analytics Dashboard" in res_analytics.output
    assert "Total Analyzed Files: 1" in res_analytics.output
    assert "Privacy Risk Breakdown" in res_analytics.output

    # Test stats shortcut
    res_stats = runner.invoke(cli.app, ["--db-path", str(db_file), "stats"])
    assert res_stats.exit_code == 0
    assert "TraceLens Analytics Dashboard" in res_stats.output


def test_cli_config_and_optimize(tmp_path):
    """Test 'tracelens config' and 'tracelens config optimize'."""
    runner = CliRunner()
    db_file = tmp_path / "test.db"

    res_cfg = runner.invoke(cli.app, ["--db-path", str(db_file), "config"])
    assert res_cfg.exit_code == 0
    assert "Configuration" in res_cfg.output
    assert db_file.name in res_cfg.output

    res_opt = runner.invoke(cli.app, ["--db-path", str(db_file), "config", "optimize"])
    assert res_opt.exit_code == 0
    assert "SQLite optimization completed" in res_opt.output


def test_cli_report_from_history_record_id(tmp_path):
    """Test generating a report using a database record ID as source."""
    runner = CliRunner()
    db_file = tmp_path / "test.db"
    test_file = tmp_path / "from_id.txt"
    test_file.write_text("ID Report Content", encoding="utf-8")
    out_dir = tmp_path / "reports_from_id"

    # Extract to populate DB
    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

    # Generate report by ID 1
    result = runner.invoke(
        cli.app,
        ["--db-path", str(db_file), "report", "1", "--format", "txt", "--output-dir", str(out_dir)],
    )
    assert result.exit_code == 0
    assert "Record ID: 1" in result.output
    assert len(list(out_dir.glob("*.txt"))) == 1


def test_cli_edit_with_metadata_json_file(tmp_path):
    """Test 'tracelens edit' using --metadata-file JSON payload."""
    runner = CliRunner()
    db_file = tmp_path / "test.db"
    test_file = tmp_path / "target.txt"
    test_file.write_text("Hello Target", encoding="utf-8")

    meta_json = tmp_path / "payload.json"
    meta_json.write_text(json.dumps({"Author": "JSONAuthor", "Title": "JSONTitle"}), encoding="utf-8")

    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

    result = runner.invoke(
        cli.app,
        ["--db-path", str(db_file), "edit", str(test_file), "--metadata-file", str(meta_json)],
    )
    assert result.exit_code == 0
    assert "Author: JSONAuthor" in result.output
    assert "Title: JSONTitle" in result.output


def test_cli_export_formats_csv_xml(tmp_path):
    """Test 'tracelens export' with CSV and XML formats."""
    runner = CliRunner()
    db_file = tmp_path / "test.db"
    test_file = tmp_path / "sample.txt"
    test_file.write_text("data", encoding="utf-8")

    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

    csv_out = tmp_path / "export.csv"
    res_csv = runner.invoke(cli.app, ["--db-path", str(db_file), "export", "csv", "--output", str(csv_out)])
    assert res_csv.exit_code == 0
    assert csv_out.exists()

    xml_out = tmp_path / "export.xml"
    res_xml = runner.invoke(cli.app, ["--db-path", str(db_file), "export", "xml", "--output", str(xml_out)])
    assert res_xml.exit_code == 0
    assert xml_out.exists()


def test_cli_analytics_with_filters(tmp_path):
    """Test 'tracelens analytics' with query and file-type filters."""
    runner = CliRunner()
    db_file = tmp_path / "test.db"
    test_file = tmp_path / "filtered_analytics.txt"
    test_file.write_text("analytics filter testing", encoding="utf-8")

    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

    res = runner.invoke(
        cli.app,
        ["--db-path", str(db_file), "analytics", "--query", "filtered", "--file-type", "txt", "--date-range", "all"],
    )
    assert res.exit_code == 0
    assert "TraceLens Analytics Dashboard" in res.output
    assert "Total Analyzed Files: 1" in res.output


def test_cli_logs_command():
    """Test 'tracelens logs' CLI command."""
    runner = CliRunner()
    res_path = runner.invoke(cli.app, ["logs", "--path"])
    assert res_path.exit_code == 0
    assert ".log" in res_path.output

    res_lines = runner.invoke(cli.app, ["logs", "--lines", "10"])
    assert res_lines.exit_code == 0


def test_cli_help_command_general():
    """Test 'tracelens help' displaying pipeline and command reference."""
    runner = CliRunner()
    res = runner.invoke(cli.app, ["help"])
    assert res.exit_code == 0
    assert "TraceLens CLI Workflow Pipeline" in res.output
    assert "Command Reference" in res.output
    assert "Common Operational Workflows" in res.output
    assert "extract" in res.output
    assert "analyze" in res.output
    assert "sanitize" in res.output
    assert "report" in res.output
    assert "export" in res.output


def test_cli_help_command_topic():
    """Test 'tracelens help <command>' deep-dive output."""
    runner = CliRunner()
    res_extract = runner.invoke(cli.app, ["help", "extract"])
    assert res_extract.exit_code == 0
    assert "Command Guide: tracelens extract" in res_extract.output
    assert "Syntax" in res_extract.output
    assert "tracelens extract <targets...> [OPTIONS]" in res_extract.output
    assert "--no-save" in res_extract.output
    assert "Examples" in res_extract.output

    res_sanitize = runner.invoke(cli.app, ["help", "sanitize"])
    assert res_sanitize.exit_code == 0
    assert "Command Guide: tracelens sanitize" in res_sanitize.output
    assert "--dry-run" in res_sanitize.output

    res_report = runner.invoke(cli.app, ["help", "report"])
    assert res_report.exit_code == 0
    assert "Command Guide: tracelens report" in res_report.output
    assert "--format" in res_report.output


def test_cli_help_command_unknown_topic():
    """Test 'tracelens help <invalid>' shows warning and general reference."""
    runner = CliRunner()
    res = runner.invoke(cli.app, ["help", "nonexistent_command"])
    assert res.exit_code == 0
    assert "Unknown Command or Topic" in res.output
    assert "Available topics:" in res.output
    assert "Command Reference" in res.output


def test_cli_no_args_suggests_help():
    """Test running 'tracelens' without arguments suggests tracelens help."""
    runner = CliRunner()
    res = runner.invoke(cli.app, [])
    assert res.exit_code == 0
    assert "tracelens help" in res.output


# ==============================================================================
# CLI/UX Hardening Pass Tests (Argparse, Validation, Error Handling, Batch, Verbose)
# ==============================================================================


def test_argparse_build_parser_and_help(capsys):
    """Test 'tracelens --help' and 'tracelens extract --help' via argparse."""
    import argparse

    parser = cli.build_parser()
    assert isinstance(parser, argparse.ArgumentParser)

    code_root = cli.main(["--help"])
    out_root = capsys.readouterr().out
    assert code_root == cli.EXIT_SUCCESS
    assert "usage: tracelens" in out_root
    assert "extract" in out_root
    assert "analyze" in out_root
    assert "search" in out_root
    assert "report" in out_root
    assert "batch" in out_root

    code_ext = cli.main(["extract", "--help"])
    out_ext = capsys.readouterr().out
    assert code_ext == cli.EXIT_SUCCESS
    assert "usage: tracelens extract" in out_ext
    assert "FILE" in out_ext
    assert "--no-save" in out_ext
    assert "Examples:" in out_ext


def test_cli_version_flag(capsys):
    """Test 'tracelens --version' outputs clean version string from centralized source."""
    from src import __version__

    code = cli.main(["--version"])
    out = capsys.readouterr().out.strip()
    assert code == cli.EXIT_SUCCESS
    assert out == f"TraceLens {__version__}"


def test_cli_invalid_command(capsys):
    """Test 'tracelens invalid-command' returns exit code 2 and clear error."""
    code = cli.main(["invalid-command"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_INVALID_ARGS
    assert "Invalid command or argument" in out
    assert "Use 'tracelens --help' for usage information." in out
    assert "Traceback (most recent call last)" not in out


def test_cli_missing_arguments(capsys):
    """Test 'tracelens extract' with missing file argument returns exit code 2."""
    code = cli.main(["extract"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_INVALID_ARGS
    assert "Invalid command or argument" in out
    assert "Use 'tracelens extract --help' for usage information." in out
    assert "Traceback (most recent call last)" not in out


def test_cli_extract_nonexistent_file(capsys):
    """Test 'tracelens extract nonexistent_file.jpg' returns exit code 3 and clear message."""
    code = cli.main(["extract", "nonexistent_file.jpg"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_FILE_ERROR
    assert "File not found: nonexistent_file.jpg" in out
    assert "Use 'tracelens extract --help' for usage information." in out
    assert "Traceback (most recent call last)" not in out


def test_cli_extract_directory_where_file_expected(tmp_path, capsys):
    """Test 'tracelens extract some_directory/' rejects directory when a file is expected."""
    some_dir = tmp_path / "some_directory"
    some_dir.mkdir()

    code = cli.main(["extract", str(some_dir)])
    out = capsys.readouterr().out
    assert code == cli.EXIT_FILE_ERROR
    assert "Path is a directory, expected a file" in out
    assert "Use 'tracelens extract --help' for usage information." in out
    assert "Traceback (most recent call last)" not in out


def test_cli_invalid_report_id(capsys):
    """Test 'tracelens report abc' validates numeric ID before calling DB and returns exit code 2."""
    code = cli.main(["report", "abc"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_INVALID_ARGS
    assert "Invalid record ID 'abc': must be an integer." in out
    assert "Use 'tracelens report --help' for usage information." in out

    code_neg = cli.main(["report", "-5"])
    out_neg = capsys.readouterr().out
    assert code_neg == cli.EXIT_INVALID_ARGS
    assert "Invalid record ID '-5': must be a positive integer." in out_neg


def test_cli_report_nonexistent_record_id_returns_db_error(tmp_path, capsys):
    """Test 'tracelens report 99999' when record does not exist in DB returns exit code 4."""
    db_file = tmp_path / "empty.db"
    code = cli.main(["--db-path", str(db_file), "report", "99999"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_DATABASE_ERROR
    assert "No history record found for ID 99999" in out


def test_cli_search_command_and_validation(tmp_path, capsys):
    """Test 'tracelens search <query>' and empty search query rejection."""
    db_file = tmp_path / "search.db"
    sample = tmp_path / "forensic_evidence.txt"
    sample.write_text("confidential payload", encoding="utf-8")

    # Reject empty/whitespace query
    code_empty = cli.main(["--db-path", str(db_file), "search", "   "])
    out_empty = capsys.readouterr().out
    assert code_empty == cli.EXIT_INVALID_ARGS
    assert "Search query cannot be empty." in out_empty

    # Populate DB and search
    assert cli.main(["--db-path", str(db_file), "extract", str(sample)]) == cli.EXIT_SUCCESS
    capsys.readouterr()

    code_hit = cli.main(["--db-path", str(db_file), "search", "forensic_evidence"])
    out_hit = capsys.readouterr().out
    assert code_hit == cli.EXIT_SUCCESS
    assert "Search completed" in out_hit
    assert "forensic_evidence.txt" in out_hit

    code_miss = cli.main(["--db-path", str(db_file), "search", "no_such_record_xyz"])
    out_miss = capsys.readouterr().out
    assert code_miss == cli.EXIT_SUCCESS
    assert "No matching records found" in out_miss


def test_cli_extract_success_summary_format(tmp_path, capsys):
    """Test 'tracelens extract' outputs concise success summary with File, Format, Metadata fields, Record ID."""
    db_file = tmp_path / "summary.db"
    sample = tmp_path / "example.txt"
    sample.write_text("Hello forensic world", encoding="utf-8")

    code = cli.main(["--db-path", str(db_file), "extract", str(sample)])
    out = capsys.readouterr().out
    assert code == cli.EXIT_SUCCESS
    assert "Metadata extraction completed" in out
    assert f"File: {sample.name}" in out
    assert "Format: TXT" in out
    assert "Metadata fields:" in out
    assert "Record ID: 1" in out


def test_cli_verbose_mode_diagnostics(tmp_path, capsys):
    """Test '-v / --verbose' outputs diagnostic INFO log steps."""
    db_file = tmp_path / "verbose.db"
    sample = tmp_path / "verbose_sample.txt"
    sample.write_text("Verbose test content", encoding="utf-8")

    # Normal mode should not include [INFO] diagnostic lines
    code_normal = cli.main(["--db-path", str(db_file), "extract", str(sample)])
    out_normal = capsys.readouterr().out
    assert code_normal == cli.EXIT_SUCCESS
    assert "[INFO] Validating file:" not in out_normal

    # Verbose mode should include [INFO] diagnostic lines
    code_verbose = cli.main(["-v", "--db-path", str(db_file), "extract", str(sample)])
    out_verbose = capsys.readouterr().out
    assert code_verbose == cli.EXIT_SUCCESS
    assert f"[INFO] Validating file: {sample.name}" in out_verbose
    assert "[INFO] File size:" in out_verbose
    assert "[INFO] Extracting metadata" in out_verbose
    assert "[INFO] Storing metadata in database" in out_verbose


def test_cli_unexpected_error_handling_normal_vs_verbose(tmp_path, monkeypatch, capsys):
    """Test unexpected exception produces clean message in normal mode and traceback in verbose mode."""
    sample = tmp_path / "boom.txt"
    sample.write_text("boom", encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("Simulated internal parser crash")

    container = cli.get_services()
    monkeypatch.setattr(container.extraction, "extract_file", _boom)
    cli.set_services(container)

    # Normal mode: no Python traceback exposed
    code_normal = cli.main(["extract", str(sample)])
    out_normal = capsys.readouterr().out
    assert code_normal == cli.EXIT_GENERAL_ERROR
    assert "An unexpected error occurred while processing the file." in out_normal
    assert "Traceback (most recent call last)" not in out_normal

    # Verbose mode: includes diagnostic exception details & traceback
    code_verbose = cli.main(["-v", "extract", str(sample)])
    out_verbose = capsys.readouterr().out
    assert code_verbose == cli.EXIT_GENERAL_ERROR
    assert "Simulated internal parser crash" in out_verbose
    assert "Traceback (most recent call last)" in out_verbose


def test_cli_batch_command_valid_empty_and_partial_failure(tmp_path, monkeypatch, capsys):
    """Test 'tracelens batch' with valid directory, empty directory, and individual file failure."""
    db_file = tmp_path / "batch.db"

    # 1. Empty directory
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    code_empty = cli.main(["--db-path", str(db_file), "batch", str(empty_dir)])
    out_empty = capsys.readouterr().out
    assert code_empty == cli.EXIT_SUCCESS
    assert "No files were found to process." in out_empty
    assert "Total: 0" in out_empty
    assert "Successful: 0" in out_empty
    assert "Failed: 0" in out_empty

    # 2. Valid directory with multiple files
    batch_dir = tmp_path / "samples"
    batch_dir.mkdir()
    f1 = batch_dir / "image1.txt"
    f2 = batch_dir / "document2.txt"
    f1.write_text("file 1 content", encoding="utf-8")
    f2.write_text("file 2 content", encoding="utf-8")

    code_ok = cli.main(["--db-path", str(db_file), "batch", str(batch_dir)])
    out_ok = capsys.readouterr().out
    assert code_ok == cli.EXIT_SUCCESS
    assert "Processing 1/2: document2.txt" in out_ok
    assert "Processing 2/2: image1.txt" in out_ok
    assert "Batch processing complete" in out_ok
    assert "Total: 2" in out_ok
    assert "Successful: 2" in out_ok
    assert "Failed: 0" in out_ok

    # 3. Individual file failure does not abort entire batch
    container = cli.get_services()
    orig_extract = container.extraction.extract_file

    def _flaky_extract(path_str: str, persist: bool = True):
        if path_str.endswith("image1.txt"):
            return ExtractionResult(file_path=path_str, success=False, error="Corrupted header")
        return orig_extract(path_str, persist=persist)

    monkeypatch.setattr(container.extraction, "extract_file", _flaky_extract)
    cli.set_services(container)

    code_partial = cli.main(["--db-path", str(db_file), "batch", str(batch_dir)])
    out_partial = capsys.readouterr().out
    assert code_partial == cli.EXIT_SUCCESS
    assert "Total: 2" in out_partial
    assert "Successful: 1" in out_partial
    assert "Failed: 1" in out_partial
    assert "image1.txt: Corrupted header" in out_partial

    # 4. File passed where directory is expected in batch
    code_bad_dir = cli.main(["batch", str(f1)])
    out_bad_dir = capsys.readouterr().out
    assert code_bad_dir == cli.EXIT_FILE_ERROR
    assert "Path is a file, expected a directory" in out_bad_dir



