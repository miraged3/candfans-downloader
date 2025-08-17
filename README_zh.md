[English](README.md) | [中文](README_zh.md)

# CandFans 下载器

CandFans Downloader 是一个用于从你的 [candfans.jp](https://candfans.jp/) 订阅中归档内容的 Python 应用程序。它提供桌面图形界面，登录你的账户，获取已订阅创作者的帖子，并将视频文件保存到本地。

## 功能

- 内嵌登录窗口自动捕获 Cookie 和 XSRF 令牌，并将其保存到 `config.yaml`。
- 配置对话框可编辑 API 端点、认证头以及下载目录。
- 从你的订阅加载账户列表并获取时间线帖子。
- 按关键字、月份和媒体类型（`mp4` 或 `m3u8`）过滤帖子。
- 批量下载，带进度条、暂停/继续和取消功能。
- 使用 `ffmpeg` 将 `m3u8` 流合并为 MP4 文件。

## 运行环境

- Python 3.8+
- `requirements.txt` 中的依赖
- `PATH` 中可用的 [FFmpeg](https://ffmpeg.org/)

## 安装

```bash
git clone https://github.com/<repo>/candfans-downloader.git
cd candfans-downloader
python -m venv venv   # 可选
source venv/bin/activate  # Windows 上使用 venv\\Scripts\\activate
pip install -r requirements.txt
```

确保已安装并可访问 `ffmpeg`。

## 配置

程序首次运行会生成 `config.yaml`。在 GUI 中打开 **Config** 来填写：

| 字段                  | 说明                                     |
|-----------------------|------------------------------------------|
| `base_url`            | 订阅列表的 API 端点                      |
| `get_users_url`       | 根据 code 获取用户信息的 API 端点        |
| `get_timeline_url`    | 时间线帖子的 API 端点                    |
| `headers.x-xsrf-token`| 来自 CandFans 的 XSRF 令牌               |
| `cookie`              | 登录 Cookie                              |
| `download_dir`        | 保存文件的文件夹                         |

### 自动登录

在 GUI 中点击 **Login**。会弹出浏览器窗口；登录后，应用会捕获 Cookie 和 XSRF 令牌，并自动保存到 `config.yaml`。

### 手动获取令牌

如果自动登录失败，可手动获取这些值：

1. 使用 Chrome 登录 CandFans。
2. 打开开发者工具（`F12`）→ **Network** 并刷新页面。
3. 找到 `get-user-mine` 请求，右键选择 **Copy as cURL**。
4. 从命令中提取 `x-xsrf-token` 和 Cookie 字符串并粘贴到 `config.yaml` 中。

![令牌位置](doc/image1.png)
![Cookie 位置](doc/image2.png)

## 运行

启动 GUI：

```bash
python main.py
```

典型流程：

1. **Login** – 捕获认证 Cookie。
2. **Load account list** – 获取所有已订阅的创作者。
3. **Fetch posts** – 选择账户并选择获取的页数或全部；可选关键字、月份和类型过滤。
4. **Download** – 选择想要的帖子并点击 *Start Download*。按需使用 *Pause* 或 *Cancel*。下载内容保存到 `download_dir`。

## 编程使用

核心下载逻辑位于 `downloader.download_and_merge()`，该函数接受媒体 URL，并使用 `ffmpeg` 将 `m3u8` 片段合并。你可以在自己的脚本中导入并使用此函数。

---

*CandFans Downloader 仅用于对合法获取的内容进行个人归档。*

