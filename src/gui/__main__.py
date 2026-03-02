import os
import sys

if __package__ in (None, ""):
    # Support direct script execution (e.g. PyInstaller entry script).
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from gui import main
else:
    from . import main

if __name__ == "__main__":
    main()
