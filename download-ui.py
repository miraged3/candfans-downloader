import sys
import yaml

from config import check_requirements, load_config
from gui import DownloaderGUI


def main():
    try:
        load_config()
    except FileNotFoundError:
        print("错误：未找到 config.yaml")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"配置文件格式错误: {e}")
        sys.exit(1)

    if not check_requirements():
        print("\n请先安装缺少的依赖：")
        print("pip install -r requirements.txt")
        sys.exit(1)

    app = DownloaderGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
