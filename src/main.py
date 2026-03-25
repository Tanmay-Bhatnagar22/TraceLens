"""Main entry point for TraceLens application."""

from gui import run_gui
from tkinter import messagebox, Tk


def main() -> None:
    """Launch the TraceLens GUI application.
    
    Entry point for the application. Initializes and runs the Tkinter-based GUI.
    """
    try:
        run_gui()
    except Exception as exc:
        # Avoid crashing silently; surface the startup issue.
        try:
            root = Tk()
            root.withdraw()
            messagebox.showerror("TraceLens Startup Error", str(exc))
            root.destroy()
        except Exception:
            pass
        print(f"Failed to launch GUI: {exc}")


if __name__ == "__main__":
    main()
