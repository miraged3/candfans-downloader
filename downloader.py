import os
import re
import shutil
import subprocess
import time
from urllib.parse import urljoin

import requests
from tqdm import tqdm

from network import safe_get
from config import HEADERS

ffmpeg_path = shutil.which("ffmpeg")
if ffmpeg_path is None:
    raise RuntimeError("未找到 ffmpeg。请先安装 ffmpeg 并确保其在系统 PATH 中。")


def sanitize_filename(filename: str) -> str:
    """Replace characters invalid on most filesystems."""
    return re.sub(r'[<>:"/\\|?*]', '_', filename).strip()


def ensure_dir(path: str) -> None:
    """Create directory if it does not exist."""
    os.makedirs(path, exist_ok=True)


def _download_ts_segment(ts_url, ts_path, idx, total, log, pause_event, cancel_event):
    def _log(msg):
        if log:
            log(msg)
        else:
            print(msg)

    def _wait_if_paused():
        if pause_event is not None:
            pause_event.wait()

    def _should_cancel():
        return cancel_event is not None and cancel_event.is_set()

    try:
        resp = safe_get(ts_url, headers=HEADERS, stream=True)
        resp.raise_for_status()
    except requests.exceptions.SSLError as e:
        _log(f"[重试中] TS {idx} SSL 错误: {e}")
        resp = safe_get(ts_url, headers=HEADERS, stream=True)
        resp.raise_for_status()

    with open(ts_path, "wb") as ts_f:
        for chunk in resp.iter_content(1024 * 1024):
            if _should_cancel():
                _log("[取消] 用户已取消（TS 下载中）。")
                raise RuntimeError("Cancelled")
            _wait_if_paused()
            if chunk:
                ts_f.write(chunk)

    if log is None:
        # 进度条由 tqdm 控制，无需手动输出
        pass
    else:
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
    """

    def _log(msg):
        if log:
            log(msg)
        else:
            print(msg)

    def _wait_if_paused():
        if pause_event is not None:
            pause_event.wait()

    def _should_cancel():
        return cancel_event is not None and cancel_event.is_set()

    def _check_cancel_or_pause():
        if _should_cancel():
            _log("[取消] 用户已取消（TS 列表下载前）。")
            raise RuntimeError("Cancelled")
        _wait_if_paused()

    ensure_dir(target_dir)

    # ---- direct mp4 ----
    if url_type == "mp4":
        output_path = os.path.join(target_dir, output_name + ".mp4")
        _log(f"[下载 MP4] {output_path}")
        resp = safe_get(file_url, headers=HEADERS, stream=True)
        resp.raise_for_status()
        total_size = int(resp.headers.get("content-length", 0)) or None
        with open(output_path, "wb") as f:
            if log is None:
                with tqdm(total=total_size or 0, unit="B", unit_scale=True, desc=output_name) as pbar:
                    for chunk in resp.iter_content(1024 * 1024):
                        if _should_cancel():
                            _log("[取消] 用户已取消（mp4）。")
                            raise RuntimeError("Cancelled")
                        _wait_if_paused()
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            else:
                downloaded = 0
                for chunk in resp.iter_content(1024 * 1024):
                    if _should_cancel():
                        _log("[取消] 用户已取消（mp4）。")
                        raise RuntimeError("Cancelled")
                    _wait_if_paused()
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            _log(f"[进度] {output_name}: {downloaded * 100 // total_size}%")
        _log(f"[下载完成] {output_path}")
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
                sub_url = sub_1 if sub_1.startswith("http") else urljoin(base, sub_1)
                return download_and_merge(
                    sub_url,
                    target_dir,
                    output_name,
                    "m3u8",
                    log=log,
                    pause_event=pause_event,
                    cancel_event=cancel_event,
                    on_ffmpeg=on_ffmpeg,
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
        if log is None:
            with tqdm(total=total, unit="ts", desc="TS 下载") as pbar:
                for idx, ts in enumerate(ts_urls):
                    if _should_cancel():
                        _check_cancel_or_pause()

                    ts_name = f"{idx:04d}.ts"
                    ts_path = os.path.join(target_dir, ts_name)
                    _download_ts_segment(ts, ts_path, idx, total, log, pause_event, cancel_event)
                    list_f.write(f"file '{ts_name}'\n")
                    pbar.update(1)
        else:
            for idx, ts in enumerate(ts_urls):
                if _should_cancel():
                    _check_cancel_or_pause()

                ts_name = f"{idx:04d}.ts"
                ts_path = os.path.join(target_dir, ts_name)
                _download_ts_segment(ts, ts_path, idx, total, log, pause_event, cancel_event)
                list_f.write(f"file '{ts_name}'\n")

    output_path = os.path.join(target_dir, output_name + ".mp4")

    def _run_ffmpeg(command):
        if log is None and pause_event is None and cancel_event is None and on_ffmpeg is None:
            subprocess.run(command, check=True)
        else:
            try:
                p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                if on_ffmpeg:
                    on_ffmpeg(p)
                while True:
                    if _should_cancel():
                        _log("[取消] 终止 FFmpeg 进程...")
                        try:
                            p.terminate()
                        except ProcessLookupError:
                            pass  # 进程已经结束
                        try:
                            p.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            try:
                                p.kill()
                            except ProcessLookupError:
                                pass  # 进程已经结束
                        raise RuntimeError("Cancelled")
                    _wait_if_paused()
                    ret = p.poll()
                    if ret is not None:
                        if ret != 0:
                            raise subprocess.CalledProcessError(ret, command)
                        break
                    time.sleep(0.2)
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
        _run_ffmpeg(cmd)
    except subprocess.CalledProcessError as e:
        _log(f"警告：FFmpeg 合并失败，尝试重新编码: {e}")
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
        _run_ffmpeg(cmd)

    _log(f"[合并完成] {output_path}")

    for filename in os.listdir(target_dir):
        if filename.endswith(".ts") or filename.endswith(".m3u8") or filename == "filelist.txt":
            os.remove(os.path.join(target_dir, filename))
    _log(f"[清理] 中间文件已删除")
    return None
