import os
import re
import shutil
import subprocess
from urllib.parse import urljoin

import requests
import yaml
from tqdm import tqdm

from network import safe_get

from config import HEADERS, cfg, check_requirements, load_config


try:
    load_config()
except FileNotFoundError:
    print("错误：未找到 config.yaml")
    exit(1)
except yaml.YAMLError as e:
    print(f"配置文件格式错误: {e}")
    exit(1)

import sys


# 入口前检查依赖
ffmpeg_path = shutil.which("ffmpeg")
if ffmpeg_path is None:
    print("错误：未找到 ffmpeg。请先安装 ffmpeg 并确保其在系统 PATH 中。")
    exit(1)


# 清理文件名中的非法字符
def sanitize_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', '_', filename).strip()


# 获取订阅列表
def get_subscription_list():
    resp = safe_get(cfg["base_url"], headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


# 解析订阅列表
def parse_subscription_list(resp_json):
    subs = []
    for item in resp_json.get("data", []):
        subs.append(
            {
                "user_code": item["user_code"],
                "plan_id": item["plan_id"],
            }
        )
    return subs


# 根据 user_code 获取用户信息
def get_user_info_by_code(user_code):
    resp = safe_get(cfg["get_users_url"], headers=HEADERS, params={"user_code": user_code})
    resp.raise_for_status()
    data = resp.json()
    user = data["data"]["user"]
    return {
        "user_code": user["user_code"],
        "username": user["username"],
        "user_id": user["id"],
    }


# 获取时间线
def get_timeline(user_id, page=1, record=12):
    params = {
        "user_id": user_id,
        "sort_order": "new",
        "record": record,
        "page": page,
        "post_type[0]": 1,
    }
    resp = safe_get(cfg["get_timeline_url"], headers=HEADERS, params=params)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])


# 创建目录
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


# 下载并合并函数
def download_and_merge(file_url, target_dir, output_name, url_type='m3u8'):
    ensure_dir(target_dir)

    # 如果是mp4文件，直接下载
    if url_type == 'mp4':
        output_path = os.path.join(target_dir, output_name)
        print(f"[下载 MP4] {output_path}")
        resp = safe_get(file_url, headers=HEADERS, stream=True)
        resp.raise_for_status()
        total_size = int(resp.headers.get("content-length", 0))
        with open(output_path, "wb") as f, tqdm(
                total=total_size, unit='B', unit_scale=True, desc=output_name
        ) as pbar:
            for chunk in resp.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
        print(f"[下载完成] {output_path}")
        return None

    # 下载 m3u8 文本
    r = safe_get(file_url, headers=HEADERS)
    r.raise_for_status()
    m3u8_text = r.text
    m3u8_filename = os.path.join(target_dir, os.path.basename(file_url))
    with open(m3u8_filename, "w", encoding="utf-8") as f:
        f.write(m3u8_text)

    # 判断 Master Playlist
    lines = [l.strip() for l in m3u8_text.splitlines() if l.strip()]
    if any(l.startswith("#EXT-X-STREAM-INF") for l in lines):
        for i, l in enumerate(lines):
            if l.startswith("#EXT-X-STREAM-INF"):
                sub_1 = lines[i + 1]
                base = file_url.rsplit("/", 1)[0] + "/"
                sub_url = sub_1 if sub_1.startswith("http") else urljoin(base, sub_1)
                return download_and_merge(sub_url, target_dir, output_name)

    # 解析 TS 列表
    base = file_url.rsplit("/", 1)[0] + "/"
    ts_urls = [(l if l.startswith("http") else urljoin(base, l)) for l in lines if not l.startswith("#")]

    # 下载 TS 并生成合并列表
    filelist_path = os.path.join(target_dir, "filelist.txt")
    with open(filelist_path, "w", encoding="utf-8") as list_f:
        with tqdm(total=len(ts_urls), unit='ts', desc="TS 下载") as pbar:
            for idx, ts in enumerate(ts_urls):
                ts_name = f"{idx:04d}.ts"
                ts_path = os.path.join(target_dir, ts_name)
                try:
                    resp = safe_get(ts, headers=HEADERS, stream=True)
                    resp.raise_for_status()
                except requests.exceptions.SSLError as e:
                    print(f"[重试中] TS {idx} SSL 错误: {e}")
                    resp = safe_get(ts, headers=HEADERS, stream=True)
                    resp.raise_for_status()
                with open(ts_path, "wb") as ts_f:
                    for chunk in resp.iter_content(1024 * 1024):
                        if chunk:
                            ts_f.write(chunk)
                list_f.write(f"file '{ts_name}'\n")
                pbar.update(1)

    # 合并 TS
    output_path = os.path.join(target_dir, output_name)
    cmd = [ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", filelist_path,
           "-c", "copy", "-ignore_unknown", "-fflags", "+genpts", output_path]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"警告：FFmpeg 合并失败，尝试使用重新编码方式: {e}")
        cmd = [ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", filelist_path,
               "-c:v", "libx264", "-c:a", "aac", "-ignore_unknown", "-fflags", "+genpts", output_path]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"错误：FFmpeg 重新编码也失败了: {e}")
            raise
    print(f"[合并完成] {output_path}")

    # 清理中间文件
    for filename in os.listdir(target_dir):
        if filename.endswith(".ts") or filename.endswith(".m3u8") or filename == "filelist.txt":
            os.remove(os.path.join(target_dir, filename))
    print(f"[清理] 中间文件已删除")
    return None


if __name__ == "__main__":
    if not check_requirements():
        print("\n请先安装缺少的依赖：")
        print("pip install -r requirements.txt")
        sys.exit(1)
    subs_resp = get_subscription_list()
    subs_1 = parse_subscription_list(subs_resp)

    for sub in subs_1:
        info = get_user_info_by_code(sub["user_code"])
        user_dir = os.path.join(cfg["download_dir"], info["user_code"])
        page_1 = 1
        while True:
            timeline = get_timeline(info["user_id"], page=page_1)
            for post_1 in timeline:
                file_type = ''
                attachments = post_1.get("attachments") or []
                if not attachments:
                    continue
                url = attachments[0].get("default")
                if url and url.endswith(".m3u8"):
                    file_type = 'm3u8'
                elif url and url.endswith(".mp4"):
                    file_type = 'mp4'
                else:
                    print(f"链接：{url} 的格式不被支持！")
                    continue
                pid = post_1["post_id"]
                ym = post_1.get("month", "unknown_month")
                title = sanitize_filename(post_1.get("title", "untitled"))
                target = os.path.join(str(user_dir), ym, str(title))
                out_name = f"{title}_{pid}.mp4"
                print(f"\n== 开始下载 {info['user_code']} {ym} {title} ({pid}) ==")
                if os.path.exists(os.path.join(target, out_name)):
                    print(f"[跳过] {out_name} 已存在")
                    continue
                download_and_merge(url, target, out_name, file_type)
            page_1 += 1
            if len(timeline) < 12:
                break
