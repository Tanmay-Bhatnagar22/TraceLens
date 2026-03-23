import sys
from pathlib import Path
import types
import subprocess

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
