"""GUI package exposing :class:`DownloaderGUI` and a convenient :func:`main` launcher."""

import sys
import yaml
import ctypes

from core.config import check_requirements, load_config
from core.app_log import show_error, log

__all__ = ["DownloaderGUI", "ConfigDialog", "main"]


def main() -> None:
    """Load configuration, verify requirements and launch the GUI."""
    from .main import DownloaderGUI

    try:
        load_config()
    except yaml.YAMLError as e:
        msg = f"Invalid configuration file format: {e}"
        show_error(msg, title="Config Error")
        log(msg)
        sys.exit(1)

    # if not check_requirements():
    #     print("\nPlease install missing dependencies:")
    #     print("pip install -r requirements.txt")
    #     sys.exit(1)

    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    app = DownloaderGUI()
    app.mainloop()


def __getattr__(name):
    if name == "DownloaderGUI":
        from .main import DownloaderGUI
        return DownloaderGUI
    if name == "ConfigDialog":
        from .config_dialog import ConfigDialog
        return ConfigDialog
    raise AttributeError(name)
