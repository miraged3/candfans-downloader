import os
import re
import shutil
import subprocess
import time
from urllib.parse import urljoin

import requests
from tqdm import tqdm

from .network import safe_get
from .config import HEADERS
from .api import get_purchased_contents, parse_purchased_contents
from .app_log import log as app_log

ffmpeg_path = shutil.which("ffmpeg")
if ffmpeg_path is None:
    raise RuntimeError(
        "ffmpeg not found. Please install ffmpeg and ensure it is in the system PATH.")


def sanitize_filename(filename: str) -> str:
    """Replace characters invalid on most filesystems."""
    # Replace invalid characters with underscore
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove leading/trailing whitespace and dots
    filename = filename.strip(' .')
    return filename


def ensure_dir(path: str) -> None:
    """Create directory if it does not exist."""
    os.makedirs(path, exist_ok=True)


def _download_ts_segment(ts_url, ts_path, idx, total, log, pause_event, cancel_event, progress_cb=None):
    def _log(msg):
        if log:
            log(msg)
        else:
            app_log(msg)

    def _wait_if_paused():
        if pause_event is not None:
            pause_event.wait()

    def _should_cancel():
        return cancel_event is not None and cancel_event.is_set()

    try:
        resp = safe_get(ts_url, headers=HEADERS, stream=True)
        resp.raise_for_status()
    except requests.exceptions.SSLError as e:
        _log(f"[Retrying] TS {idx} SSL error: {e}")
        resp = safe_get(ts_url, headers=HEADERS, stream=True)
        resp.raise_for_status()

    with open(ts_path, "wb") as ts_f:
        for chunk in resp.iter_content(1024 * 1024):
            if _should_cancel():
                _log("[Cancelled] User cancelled (downloading TS segment).")
                raise RuntimeError("Cancelled")
            _wait_if_paused()
            if chunk:
                ts_f.write(chunk)

    if progress_cb:
        progress_cb(idx + 1, total)
    if log is not None:
        _log(f"[TS] {idx + 1}/{total}")


def download_and_merge(
        file_url: str,
        target_dir: str,
        output_name: str,
        url_type: str = "m3u8",
        log=None,
        pause_event=None,
        cancel_event=None,
        on_ffmpeg=None,
        progress_cb=None,
):
    """Download a video (m3u8/mp4) and merge segments via ffmpeg.

    Parameters
    ----------
    file_url: str
        URL to the video file or m3u8 playlist.
    target_dir: str
        Directory to store temporary files and final output.
    output_name: str
        Name of the resulting mp4 file.
    url_type: str
        Either "m3u8" or "mp4".
    log: callable, optional
        Logging function; defaults to ``print`` when omitted.
    pause_event: threading.Event, optional
        When provided, download will pause while the event is cleared.
    cancel_event: threading.Event, optional
        When set, the download is cancelled immediately.
    on_ffmpeg: callable, optional
        Callback receiving the ffmpeg ``Popen`` object. Called with ``None``
        when processing ends.
    progress_cb: callable, optional
        Receives ``(current, total)`` to report progress.
    """

    def _log(msg):
        if log:
            log(msg)
        else:
            app_log(msg)

    def _wait_if_paused():
        if pause_event is not None:
            pause_event.wait()

    def _should_cancel():
        return cancel_event is not None and cancel_event.is_set()

    def _check_cancel_or_pause():
        if _should_cancel():
            _log("[Cancelled] User cancelled (before downloading TS list).")
            raise RuntimeError("Cancelled")
        _wait_if_paused()

    ensure_dir(target_dir)

    # ---- direct mp4 ----
    if url_type == "mp4":
        output_path = os.path.join(target_dir, output_name + ".mp4")
        _log(f"[Download MP4] {output_path}")
        resp = safe_get(file_url, headers=HEADERS, stream=True)
        resp.raise_for_status()
        total_size = int(resp.headers.get("content-length", 0)) or None
        with open(output_path, "wb") as f:
            downloaded = 0
            if progress_cb is None and log is None:
                with tqdm(total=total_size or 0, unit="B", unit_scale=True, desc=output_name) as pbar:
                    for chunk in resp.iter_content(1024 * 1024):
                        if _should_cancel():
                            _log("[Cancelled] User cancelled (mp4).")
                            raise RuntimeError("Cancelled")
                        _wait_if_paused()
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            pbar.update(len(chunk))
            else:
                for chunk in resp.iter_content(1024 * 1024):
                    if _should_cancel():
                        _log("[Cancelled] User cancelled (mp4).")
                        raise RuntimeError("Cancelled")
                    _wait_if_paused()
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            progress_cb(downloaded, total_size or 0)
                        elif total_size and log is not None:
                            _log(
                                f"[Progress] {output_name}: {downloaded * 100 // total_size}%")
            if progress_cb and downloaded and (total_size or 0):
                progress_cb(downloaded, total_size or downloaded)
        _log(f"[Download complete] {output_path}")
        return None

    # ---- m3u8 playlist ----
    r = safe_get(file_url, headers=HEADERS)
    r.raise_for_status()
    m3u8_text = r.text
    m3u8_filename = os.path.join(target_dir, os.path.basename(file_url))
    with open(m3u8_filename, "w", encoding="utf-8") as f:
        f.write(m3u8_text)

    lines = [l.strip() for l in m3u8_text.splitlines() if l.strip()]
    if any(l.startswith("#EXT-X-STREAM-INF") for l in lines):
        for i, l in enumerate(lines):
            if l.startswith("#EXT-X-STREAM-INF"):
                sub_1 = lines[i + 1]
                base = file_url.rsplit("/", 1)[0] + "/"
                sub_url = sub_1 if sub_1.startswith(
                    "http") else urljoin(base, sub_1)
                return download_and_merge(
                    sub_url,
                    target_dir,
                    output_name,
                    "m3u8",
                    log=log,
                    pause_event=pause_event,
                    cancel_event=cancel_event,
                    on_ffmpeg=on_ffmpeg,
                    progress_cb=progress_cb,
                )

    base = file_url.rsplit("/", 1)[0] + "/"
    ts_urls = [
        (l if l.startswith("http") else urljoin(base, l))
        for l in lines
        if not l.startswith("#")
    ]

    filelist_path = os.path.join(target_dir, "filelist.txt")
    with open(filelist_path, "w", encoding="utf-8") as list_f:
        total = len(ts_urls)
        if progress_cb is None and log is None:
            with tqdm(total=total, unit="ts", desc="TS download") as pbar:
                for idx, ts in enumerate(ts_urls):
                    if _should_cancel():
                        _check_cancel_or_pause()

                    ts_name = f"{idx:04d}.ts"
                    ts_path = os.path.join(target_dir, ts_name)
                    _download_ts_segment(
                        ts, ts_path, idx, total, log, pause_event, cancel_event)
                    list_f.write(f"file '{ts_name}'\n")
                    pbar.update(1)
        else:
            for idx, ts in enumerate(ts_urls):
                if _should_cancel():
                    _check_cancel_or_pause()

                ts_name = f"{idx:04d}.ts"
                ts_path = os.path.join(target_dir, ts_name)
                _download_ts_segment(
                    ts, ts_path, idx, total, log, pause_event, cancel_event, progress_cb=progress_cb)
                list_f.write(f"file '{ts_name}'\n")

    output_path = os.path.join(target_dir, output_name + ".mp4")
    _log(
        f"[Starting FFmpeg] Merging {len(ts_urls)} TS segments into {output_path}")

    def _run_ffmpeg(command):
        if log is None and pause_event is None and cancel_event is None and on_ffmpeg is None:
            subprocess.run(command, check=True)
        else:
            try:
                p = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    universal_newlines=True, bufsize=1, encoding='utf-8', errors='replace')
                if on_ffmpeg:
                    on_ffmpeg(p)

                while True:
                    if _should_cancel():
                        _log("[Cancelled] Terminating FFmpeg process...")
                        try:
                            p.terminate()
                        except ProcessLookupError:
                            pass  # process already ended
                        try:
                            p.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            try:
                                p.kill()
                            except ProcessLookupError:
                                pass  # process already ended
                        raise RuntimeError("Cancelled")
                    _wait_if_paused()

                    # Read and discard output to prevent buffer overflow
                    if p.stdout:
                        try:
                            p.stdout.readline()
                        except:
                            pass

                    ret = p.poll()
                    if ret is not None:
                        # Read any remaining output to clean up
                        if p.stdout:
                            try:
                                p.stdout.read()
                            except:
                                pass
                        if ret != 0:
                            raise subprocess.CalledProcessError(ret, command)
                        break
                    time.sleep(0.1)
            finally:
                if on_ffmpeg:
                    on_ffmpeg(None)

    try:
        cmd = [
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            filelist_path,
            "-c",
            "copy",
            "-ignore_unknown",
            "-fflags",
            "+genpts",
            "-f",
            "mp4",
            output_path,
        ]
        _log(f"[FFmpeg Command] {' '.join(cmd)}")
        _run_ffmpeg(cmd)
    except subprocess.CalledProcessError as e:
        _log(f"Warning: FFmpeg merge failed, trying to re-encode: {e}")
        cmd = [
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            filelist_path,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-ignore_unknown",
            "-fflags",
            "+genpts",
            "-f",
            "mp4",
            output_path,
        ]
        _log(f"[FFmpeg Re-encode Command] {' '.join(cmd)}")
        _run_ffmpeg(cmd)

    _log(f"[Merge complete] {output_path}")

    for filename in os.listdir(target_dir):
        if filename.endswith(".ts") or filename.endswith(".m3u8") or filename == "filelist.txt":
            os.remove(os.path.join(target_dir, filename))
    _log(f"[Cleanup] Temporary files removed")
    return None


def download_purchased_contents(
    target_dir: str = "downloads",
    keyword: str = "",
    month_filter: str = "",
    log=None,
    pause_event=None,
    cancel_event=None,
    on_ffmpeg=None,
    progress_cb=None,
):
    """Download purchased contents from CandFans.

    Parameters
    ----------
    target_dir: str
        Base directory to store downloaded content.
    keyword: str
        Filter content by keyword in title.
    month_filter: str
        Filter content by purchase month (e.g., "2025年09月").
    log: callable, optional
        Logging function; defaults to ``print`` when omitted.
    pause_event: threading.Event, optional
        When provided, download will pause while the event is cleared.
    cancel_event: threading.Event, optional
        When set, the download is cancelled immediately.
    on_ffmpeg: callable, optional
        Callback receiving the ffmpeg ``Popen`` object.
    progress_cb: callable, optional
        Receives ``(current, total)`` to report progress.
    """

    def _log(msg):
        if log:
            log(msg)
        else:
            app_log(msg)

    def _should_cancel():
        return cancel_event is not None and cancel_event.is_set()

    try:
        _log("Fetching purchased contents...")
        resp = get_purchased_contents()
        contents = parse_purchased_contents(resp)
        _log(f"Found {len(contents)} purchased contents")
    except Exception as e:
        _log(f"[Error] Failed to fetch purchased contents: {e}")
        return

    # Apply filters
    filtered_contents = []
    for content in contents:
        if _should_cancel():
            _log("[Cancelled] User cancelled during filtering.")
            return

        # Filter by keyword
        if keyword and keyword.lower() not in content.get("title", "").lower():
            continue

        # Filter by month
        if month_filter and content.get("purchase_month", "") != month_filter:
            continue

        # Only include content with attachments
        attachments = content.get("attachments", [])
        if not attachments:
            continue

        filtered_contents.append(content)

    _log(f"After filtering: {len(filtered_contents)} contents to download")

    if not filtered_contents:
        _log("No contents to download after filtering")
        return

    # Download each content
    for i, content in enumerate(filtered_contents):
        if _should_cancel():
            _log("[Cancelled] User cancelled during download.")
            return

        title = content.get(
            "title", f"content_{content.get('post_id', 'unknown')}")
        username = content.get("username", "unknown_user")
        post_id = str(content.get("post_id", "unknown"))
        purchase_month = content.get("purchase_month", "unknown_month")

        _log(f"[{i+1}/{len(filtered_contents)}] Downloading: {username} / {title}")

        # Create directory structure: target_dir/username/post_id-title/
        user_dir = os.path.join(target_dir, sanitize_filename(username))
        content_dir = os.path.join(
            user_dir, f"{post_id}-{sanitize_filename(title)}")
        ensure_dir(content_dir)

        # Download all attachments
        attachments = content.get("attachments", [])
        for j, attachment in enumerate(attachments):
            if _should_cancel():
                _log("[Cancelled] User cancelled during attachment download.")
                return

            # Get the main URL (default quality)
            url = attachment.get("default")
            if not url:
                continue

            # Determine file type
            if url.endswith(".m3u8"):
                url_type = "m3u8"
                file_ext = "mp4"  # m3u8 will be converted to mp4
            else:
                url_type = "mp4"
                file_ext = "mp4"

            # Create filename for this attachment
            if len(attachments) > 1:
                output_name = f"{sanitize_filename(title)}_{j+1}"
            else:
                output_name = sanitize_filename(title)

            try:
                def attachment_progress_cb(current, total):
                    if progress_cb:
                        # Calculate overall progress
                        content_progress = i / len(filtered_contents)
                        attachment_progress = (
                            j + current / (total or 1)) / len(attachments)
                        overall_progress = content_progress + \
                            attachment_progress / len(filtered_contents)
                        progress_cb(int(overall_progress * 1000), 1000)

                download_and_merge(
                    url,
                    content_dir,
                    output_name,
                    url_type=url_type,
                    log=log,
                    pause_event=pause_event,
                    cancel_event=cancel_event,
                    on_ffmpeg=on_ffmpeg,
                    progress_cb=attachment_progress_cb,
                )
                _log(f"    Downloaded: {output_name}.{file_ext}")

            except Exception as e:
                _log(f"    [Failed] {output_name}: {e}")
                continue

    _log(f"[Complete] Downloaded {len(filtered_contents)} purchased contents")
