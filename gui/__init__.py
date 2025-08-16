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
        print(f"配置文件格式错误: {e}")
        sys.exit(1)

    if not check_requirements():
        print("\n请先安装缺少的依赖：")
        print("pip install -r requirements.txt")
        sys.exit(1)

    app = DownloaderGUI()
    app.mainloop()

