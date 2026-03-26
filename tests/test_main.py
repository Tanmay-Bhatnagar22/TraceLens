import sys
from pathlib import Path
import unittest.mock as mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / 'src'
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pytest
from main import main


def test_main_callable():
    """Test that main function is callable."""
    assert callable(main)


def test_main_function_exists():
    """Test that main function is defined."""
    import main as main_module
    assert hasattr(main_module, 'main')


def test_main_handles_gui_launch():
    """Test that main can be forced to launch GUI."""
    # Mock the run_gui function to prevent actual GUI launch
    with mock.patch('main.run_gui') as mock_run_gui:
        main(forced_mode='gui')
        mock_run_gui.assert_called_once()


def test_main_handles_exceptions():
    """Test that main handles GUI launch exceptions in forced GUI mode."""
    # Mock run_gui to raise an exception
    with mock.patch('main.run_gui', side_effect=Exception("GUI Error")):
        # Should not raise, just print error
        try:
            main(forced_mode='gui')
        except Exception:
            pytest.fail("main() should handle exceptions gracefully")


def test_main_forced_gui_in_terminal_skips_startup_popup():
    """Terminal-forced GUI errors should not show messagebox popups."""
    with mock.patch('main.running_in_terminal', return_value=True):
        with mock.patch('main.run_gui', side_effect=Exception("GUI Error")):
            with mock.patch('main.messagebox.showerror') as mock_showerror:
                main(forced_mode='gui')
                mock_showerror.assert_not_called()


def test_main_auto_selects_cli_when_terminal_detected():
    """Test that terminal launch path routes to CLI."""
    with mock.patch('main.running_in_terminal', return_value=True):
        with mock.patch('main.run_cli') as mock_run_cli, mock.patch('main.run_gui') as mock_run_gui:
            main()
            mock_run_cli.assert_called_once()
            mock_run_gui.assert_not_called()


def test_main_auto_selects_gui_without_terminal():
    """Test that non-terminal launch path routes to GUI."""
    with mock.patch('main.running_in_terminal', return_value=False):
        with mock.patch('main.run_cli') as mock_run_cli, mock.patch('main.run_gui') as mock_run_gui:
            main()
            mock_run_gui.assert_called_once()
            mock_run_cli.assert_not_called()
