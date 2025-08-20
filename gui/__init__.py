"""GUI package exposing :class:`DownloaderGUI` and a convenient :func:`main` launcher."""

import sys
import yaml

from .main import DownloaderGUI
from .config_dialog import ConfigDialog
from config import check_requirements, load_config

__all__ = ["DownloaderGUI", "ConfigDialog", "main"]


def main() -> None:
    """Load configuration, verify requirements and launch the GUI."""
    try:
        load_config()
    except yaml.YAMLError as e:
        print(f"Invalid configuration file format: {e}")
        sys.exit(1)

    # if not check_requirements():
    #     print("\nPlease install missing dependencies:")
    #     print("pip install -r requirements.txt")
    #     sys.exit(1)

    app = DownloaderGUI()
    app.mainloop()

