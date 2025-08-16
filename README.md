# Candfans Downloader
Downloads all the files from a Candfans.com account.

### Usage
1. Install Python 3.8+
2. Install the required modules: `pip install -r requirements.txt`
3. Install ffmpeg, and make sure it's in your PATH. In Windows, you can download it from [here](https://www.gyan.dev/ffmpeg/builds/).
4. Copy config_demo.py to config.py in project root directory.
5. Login to [Candfans](https://candfans.jp/mypage) with Chrome, and press F12, navigate to the Network tab, and refresh the page, find the request named `get-user-mine`, right click it, and click Copy as cURL(bash).
6. Paste the cURL into a text editor, find the content of `x-xsrf-token` and `-b`, then paste them into `x-xsrf-token` and `cookie` in config.py. ![image](/doc/image1.png)![image](/doc/image2.png)
7. Run `python download.py`

### 中文介绍

用于下载 Candfans.com 订阅的视频

### 使用方法

1. 安装 Python 3.8 或以上版本
2. 安装所需依赖：

   ```bash
   pip install -r requirements.txt
   ```
3. 安装 ffmpeg，并确保已添加到系统 PATH
   在 Windows 下，可从 [这里](https://www.gyan.dev/ffmpeg/builds/) 下载
4. 将 `config_demo.py` 复制到项目根目录下，命名为 `config.py`
5. 在 Chrome 中登录 [Candfans](https://candfans.jp/mypage)，按 F12 打开开发者工具，切换到 Network（网络）面板，刷新页面，找到名为 `get-user-mine` 的请求，右键点击并选择 **Copy as cURL (bash)**
6. 将复制的 cURL 命令粘贴到文本编辑器中，提取其中的 `x-xsrf-token` 和 `-b`（cookie）字段的内容，分别填入 `config.py` 中的 `x-xsrf-token` 和 `cookie` 配置项，如图所示：
   ![image](/doc/image1.png)
   ![image](/doc/image2.png)
7. 在项目根目录下运行：

   ```bash
   python download.py
   ```
