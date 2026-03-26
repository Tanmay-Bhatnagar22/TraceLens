"""Main entry point for TraceLens application."""

from __future__ import annotations

import os
import sys
from tkinter import Tk, messagebox

from cli import run_cli
from gui import run_gui


def _has_console_window() -> bool:
    """Return True when a native console window is attached (Windows only)."""
    if os.name != "nt":
        return False

    try:
        import ctypes

        return bool(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:
        return False


def _attach_parent_console() -> bool:
    """Attach to parent console for windowed builds launched from terminal."""
    if os.name != "nt":
        return False

    # Already attached.
    if _has_console_window():
        return True

    try:
        import ctypes

        ATTACH_PARENT_PROCESS = -1
        if not ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            return False

        # Rebind standard streams to the attached console.
        sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        return True
    except Exception:
        return False


def running_in_terminal() -> bool:
    """Detect whether the app was launched from a terminal/console session."""
    try:
        stdin_is_tty = bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        stdin_is_tty = False

    return stdin_is_tty or _has_console_window() or _attach_parent_console()


def _consume_mode_override() -> str | None:
    """Consume optional mode flags from argv and return forced mode if present."""
    forced_mode: str | None = None
    passthrough_args: list[str] = []

    for arg in sys.argv[1:]:
        if arg == "--cli":
            forced_mode = "cli"
            continue
        if arg == "--gui":
            forced_mode = "gui"
            continue
        passthrough_args.append(arg)

    if forced_mode:
        # Strip internal startup flags so downstream handlers receive clean args.
        sys.argv = [sys.argv[0], *passthrough_args]

    return forced_mode


def _run_gui_with_startup_dialog(show_dialog: bool = True) -> None:
    """Run GUI and surface startup exceptions with dialog/log fallback."""
    try:
        run_gui()
    except Exception as exc:
        # Avoid crashing silently; prefer dialog only for no-console launches.
        if show_dialog and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                root = Tk()
                root.withdraw()
                messagebox.showerror("TraceLens Startup Error", str(exc))
                root.destroy()
            except Exception:
                pass
        print(f"Failed to launch GUI: {exc}", file=sys.stderr)


def _log_mode(mode: str, reason: str, in_terminal: bool) -> None:
    """Log selected mode to stderr when a console is available."""
    if in_terminal:
        print(f"[TraceLens] startup mode={mode} ({reason})", file=sys.stderr)


def main(forced_mode: str | None = None) -> None:
    """Start TraceLens in CLI or GUI mode based on launch context."""
    mode = forced_mode or _consume_mode_override()
    in_terminal = running_in_terminal()

    if mode == "cli":
        _log_mode("cli", "forced", in_terminal=in_terminal)
        run_cli()
        return

    if mode == "gui":
        _log_mode("gui", "forced", in_terminal=in_terminal)
        _run_gui_with_startup_dialog(show_dialog=not in_terminal)
        return

    if in_terminal:
        _log_mode("cli", "terminal-detected", in_terminal=True)
        run_cli()
    else:
        _run_gui_with_startup_dialog(show_dialog=True)


if __name__ == "__main__":
    main()
