import json
from pathlib import Path
import subprocess
import sys

import pytest
from typer.testing import CliRunner

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import cli
from src.cli.validation import (
    CLIFileError,
    CLIValidationError,
    collect_files,
    normalize_path,
    require_directory,
    require_file,
    validate_record_id,
    validate_search_query,
)
from src.core.services import ServiceContainer, reset_service_container
from src.models import ExtractionResult


@pytest.fixture(autouse=True)
def reset_services_fixture():
    """Ensure clean service container state for each test."""
    reset_service_container()
    cli.set_services(None)
    yield
    reset_service_container()
    cli.set_services(None)


# ==============================================================================
# Validation & Path Normalization Unit Tests
# ==============================================================================


def test_normalize_path_strips_quotes_and_whitespace():
    raw = '  "C:/tmp/sample.txt"  '
    assert cli._normalize_path(raw).endswith("sample.txt")
    assert str(normalize_path(raw)).endswith("sample.txt")


def test_collect_files_returns_nested_files(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("b", encoding="utf-8")

    files = collect_files([str(tmp_path)], recursive=True, allow_directories=True)
    names = {path.name for path in files}

    assert names == {"a.txt", "b.txt"}


def test_validation_helpers_file_dir_id_and_query(tmp_path):
    sample_file = tmp_path / "valid.txt"
    sample_file.write_text("ok", encoding="utf-8")

    assert require_file(str(sample_file)) == sample_file.resolve()
    assert require_directory(str(tmp_path)) == tmp_path.resolve()

    with pytest.raises(CLIFileError):
        require_file(str(tmp_path))

    with pytest.raises(CLIFileError):
        require_directory(str(sample_file))

    assert validate_record_id("42") == 42
    with pytest.raises(CLIValidationError):
        validate_record_id("not-an-int")
    with pytest.raises(CLIValidationError):
        validate_record_id("0")

    assert validate_search_query("  confidential  ") == "confidential"
    with pytest.raises(CLIValidationError):
        validate_search_query("   ")


# ==============================================================================
# GUI Separation & Lightweight Headless CLI Tests
# ==============================================================================


def test_cli_gui_command_is_removed(capsys):
    """Verify 'tracelens gui' is no longer a valid CLI command."""
    code = cli.main(["gui"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_INVALID_ARGS
    assert "Invalid command or argument" in out
    assert "gui" not in cli.HELP_TOPICS


def test_cli_runs_without_tkinter_available(tmp_path):
    """Verify CLI commands (--version, help, --help, extract) run when tkinter is completely unavailable."""
    sample = tmp_path / "headless.txt"
    sample.write_text("Headless forensic test", encoding="utf-8")
    db_file = tmp_path / "headless.db"

    script = (
        "import sys; "
        "sys.modules['tkinter'] = None; "
        "sys.modules['tkinter.filedialog'] = None; "
        "sys.modules['tkinter.messagebox'] = None; "
        f"sys.path.insert(0, {str(PROJECT_ROOT)!r}); "
        f"sys.path.insert(0, {str(SRC_PATH)!r}); "
        "from src.cli import cli; "
        "assert 'tkinter' not in sys.modules or sys.modules['tkinter'] is None; "
        "assert cli.main(['--version']) == 0; "
        "assert cli.main(['help']) == 0; "
        "assert cli.main(['--help']) == 0; "
        f"assert cli.main(['--db-path', {str(db_file)!r}, 'extract', {str(sample)!r}]) == 0; "
        "assert sys.modules.get('tkinter') is None; "
        "assert 'src.gui' not in sys.modules; "
        "assert 'src.gui.gui' not in sys.modules; "
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"STDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}"
    assert "Metadata extraction completed" in proc.stdout


def test_removed_duplicate_and_legacy_commands_rejected(capsys):
    """Verify removed duplicate/legacy commands ('gui', 'interactive', 'stats', 'config logs') return exit code 2."""
    for argv in (["gui"], ["interactive"], ["stats"], ["config", "logs"]):
        code = cli.main(argv)
        out = capsys.readouterr().out
        assert code == cli.EXIT_INVALID_ARGS
        assert "Invalid command or argument" in out


# ==============================================================================
# Help Consolidation & Single Source of Truth Tests
# ==============================================================================


def test_help_and_dash_help_use_same_canonical_renderer(capsys):
    """Verify 'tracelens help' and 'tracelens --help' produce identical canonical output."""
    code_help = cli.main(["help"])
    out_help = capsys.readouterr().out

    code_flag = cli.main(["--help"])
    out_flag = capsys.readouterr().out

    assert code_help == cli.EXIT_SUCCESS
    assert code_flag == cli.EXIT_SUCCESS
    assert out_help == out_flag
    assert "TraceLens CLI Workflow Pipeline" in out_help
    assert "Command Reference" in out_help
    assert "Common Operational Workflows" in out_help


def test_canonical_help_topics_match_argparse_subparsers():
    """Verify every registered argparse subcommand is defined in HELP_TOPICS (single source of truth)."""
    import argparse

    parser = cli.build_parser()
    subparsers_actions = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers_actions) == 1
    registered_commands = set(subparsers_actions[0].choices.keys())
    canonical_commands = {
        name for name, info in cli.HELP_TOPICS.items() if info.get("is_command", False)
    }
    assert registered_commands == canonical_commands


def test_subcommand_dash_help_uses_argparse_and_canonical_metadata(capsys):
    """Verify 'tracelens <command> --help' works for extract, analyze, report, and batch."""
    for cmd_name in ("extract", "analyze", "report", "batch", "search"):
        code = cli.main([cmd_name, "--help"])
        out = capsys.readouterr().out
        assert code == cli.EXIT_SUCCESS
        assert f"usage: tracelens {cmd_name}" in out
        assert cli.HELP_TOPICS[cmd_name]["summary"] in out
        assert "Examples:" in out


# ==============================================================================
# Service Layer Integration Tests for CLI
# ==============================================================================


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

    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

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

    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

    res_hist = runner.invoke(cli.app, ["--db-path", str(db_file), "history"])
    assert res_hist.exit_code == 0
    assert "Recent History" in res_hist.output
    assert "hist.txt" in res_hist.output

    res_stats = runner.invoke(cli.app, ["--db-path", str(db_file), "history", "stats"])
    assert res_stats.exit_code == 0
    assert "Database Statistics" in res_stats.output
    assert "Total Records: 1" in res_stats.output

    res_del = runner.invoke(cli.app, ["--db-path", str(db_file), "history", "delete", "1", "--yes"])
    assert res_del.exit_code == 0
    assert "History Updated" in res_del.output

    res_clear = runner.invoke(cli.app, ["--db-path", str(db_file), "history", "clear", "--yes"])
    assert res_clear.exit_code == 0
    assert "History Cleared" in res_clear.output


def test_cli_analytics_command(tmp_path):
    """Test 'tracelens analytics' command."""
    runner = CliRunner()
    db_file = tmp_path / "test.db"
    test_file = tmp_path / "analytics.txt"
    test_file.write_text("some content for analytics", encoding="utf-8")

    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

    res_analytics = runner.invoke(cli.app, ["--db-path", str(db_file), "analytics"])
    assert res_analytics.exit_code == 0
    assert "TraceLens Analytics Dashboard" in res_analytics.output
    assert "Total Analyzed Files: 1" in res_analytics.output
    assert "Privacy Risk Breakdown" in res_analytics.output


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

    runner.invoke(cli.app, ["--db-path", str(db_file), "extract", str(test_file)])

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


def test_cli_export_formats_csv_xml_pdf(tmp_path):
    """Test 'tracelens export' with CSV, XML, and PDF formats via ReportService."""
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

    pdf_out = tmp_path / "export.pdf"
    res_pdf = runner.invoke(cli.app, ["--db-path", str(db_file), "export", "pdf", "--output", str(pdf_out)])
    assert res_pdf.exit_code == 0
    assert pdf_out.exists()


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


def test_tokenize_command_windows_paths():
    """Test command tokenization preserves Windows paths and quotes properly."""
    assert cli.tokenize_command(r'extract "C:\My Documents\file.pdf"') == ["extract", r"C:\My Documents\file.pdf"]
    assert cli.tokenize_command(r'analyze "C:\test.jpg" --threshold 50') == ["analyze", r"C:\test.jpg", "--threshold", "50"]
    assert cli.tokenize_command("logs -n 25") == ["logs", "-n", "25"]
    assert cli.tokenize_command("") == []


def test_cli_interactive_repl_session(monkeypatch, capsys):
    """Test interactive shell handles multiple commands, errors, empty lines, and exits cleanly."""
    import io

    # Simulate sequential user commands in interactive shell
    simulated_input = io.StringIO(
        "\n"  # empty input
        "version\n"
        "--version\n"
        "abcxyz\n"  # invalid command
        "help\n"
        "exit\n"
    )
    monkeypatch.setattr("sys.stdin", simulated_input)

    code = cli.interactive_shell()
    assert code == cli.EXIT_SUCCESS

    captured = capsys.readouterr().out
    assert "Interactive CLI" in captured
    assert "TraceLens" in captured
    assert "Unknown command: abcxyz" in captured
    assert "Goodbye!" in captured


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
    assert "TraceLens CLI Workflow Pipeline" in out_root
    assert "Command Reference" in out_root
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

    code_empty = cli.main(["--db-path", str(db_file), "search", "   "])
    out_empty = capsys.readouterr().out
    assert code_empty == cli.EXIT_INVALID_ARGS
    assert "Search query cannot be empty." in out_empty

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

    code_normal = cli.main(["--db-path", str(db_file), "extract", str(sample)])
    out_normal = capsys.readouterr().out
    assert code_normal == cli.EXIT_SUCCESS
    assert "[INFO] Validating file:" not in out_normal

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

    code_normal = cli.main(["extract", str(sample)])
    out_normal = capsys.readouterr().out
    assert code_normal == cli.EXIT_GENERAL_ERROR
    assert "An unexpected error occurred while processing the file." in out_normal
    assert "Traceback (most recent call last)" not in out_normal

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
