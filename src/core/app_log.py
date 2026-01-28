"""Simple logging bridge for routing messages into the GUI."""

from __future__ import annotations

from typing import Callable, Optional
import threading

_log_fn: Optional[Callable[[str], None]] = None
_lock = threading.Lock()


def set_logger(fn: Callable[[str], None] | None) -> None:
    """Set a callback to receive log messages."""
    global _log_fn
    with _lock:
        _log_fn = fn


def log(msg: object) -> None:
    """Log a message to the GUI if configured; otherwise print to console."""
    text = str(msg)
    with _lock:
        fn = _log_fn
    if fn is None:
        print(text)
        return
    try:
        fn(text)
    except Exception:
        print(text)


def show_error(msg: object, title: str = "Error") -> None:
    """Show a GUI error dialog if possible, otherwise log."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, str(msg))
        root.destroy()
    except Exception:
        log(msg)
