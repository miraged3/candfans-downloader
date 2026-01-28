English | [中文](docs/README_zh.md)

# CandFans Downloader

CandFans Downloader is a Python application for archiving content from your [candfans.jp](https://candfans.jp/) subscriptions. It provides a desktop GUI to log into your account, fetch posts from subscribed creators, and save video files locally.

## Requirements

- Python 3.8+
- Dependencies in `requirements.txt`
- [FFmpeg](https://ffmpeg.org/) available in your `PATH`

## Installation

```bash
git clone https://github.com/miraged3/candfans-downloader
cd candfans-downloader
pip install -r requirements.txt
```

Ensure `ffmpeg` is installed and configured in your `PATH`.

## Configuration

Running the program for the first time creates `config.yaml`. You can also open **Config** in the GUI to fill in:

| Field | Description |
|-------|-------------|
| `Base Url`      | API endpoint for the subscription list |
| `Get Users Url` | API endpoint to get user info by code |
| `Timeline Url`  | API endpoint for timeline posts |
| `Token`         | XSRF token from CandFans |
| `Cookie`        | Login cookie |
| `Download Path` | Folder where files are saved |

## Usage

### Main GUI

1. Start the program: `PYTHONPATH=src python -m main`
2. Click the login button and sign in to your CandFans account.
3. After logging in, choose between two tabs:

#### Subscription Timeline Tab

- Click `Fetch subs`; the left panel shows all subscribed accounts.
- Click `Fetch posts` to retrieve all downloadable posts. Use the filters at the top of the window as needed.
- Select posts and click `Start download`.

#### Purchased Contents Tab

- Click `Fetch purchased` to load all your purchased contents.
- Use filters to narrow down by keyword or purchase month.
- Select contents and click `Start download`.

### Manual token retrieval

If automatic login fails, you can obtain the values manually:

1. Log in to CandFans using Chrome.
2. Open Developer Tools (`F12`) → **Network** and refresh the page.
3. Find the `get-user-mine` request, right-click and choose **Copy as cURL**.
4. Extract `x-xsrf-token` and the cookie string from the command and paste them into the configuration, then click fetch posts.

![Token location](docs/images/image1.png)
![Cookie location](docs/images/image2.png)

## High DPI support

The GUI is per-monitor DPI aware on Windows, rendering crisply at 125%, 150% or 200% scaling. On older versions of Windows that lack `SetProcessDpiAwareness` or `SetProcessDPIAware`, the interface may not scale correctly and could appear blurry.

## Features

- **Subscription Timeline Downloads**: Download content from your subscribed creators
- **Purchased Content Downloads**: Download individually purchased content with filtering by keyword and month
- **GUI Interface**: User-friendly desktop application with tabbed interface
- **Filtering Options**: Filter content by keyword, month, and file type
- **Progress Tracking**: Real-time download progress with pause/resume functionality
- **Automatic Organization**: Content is organized by creator and post ID

## Future plans

- Package into a standalone executable
- Language switching

---

*CandFans Downloader is intended for personal archiving of legally obtained content.*
